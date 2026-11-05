"""KO's character-create rules for the package (RQ-002, content/character-create.md).

The package source names them in `games/<game>/character-create.json`: the
races KO's create screen offers with each one's nation and specialties (1298
`006060f0`), the face and hair counts (1298 `00604f90`), the races the package
has a player model for (`content`), the stat tables a realm may validate
against (`tables`: each a KO `Data/NewChrValue.tbl` read from the chosen front
end's inputs, its row key and the text table its refusals are worded from), the
table each front end draws (Q97 (b)), the refusals' text rows (1298 `00600750`),
the name rule (Q99) and the fixed choice a create without a race takes (Q52).
Each race also names its `looks`, the stem of its `UPC_DefaultLooks` parts, and
`player` is the race of the package's player scenes (tools/assetc/ko_player.py,
RQ-003). `models` names the races whose model the package ships in each form
a screen draws: `create`, the create screen's (front-end.bin, N3FE version 24,
RQ-158), which every race in `content` has.
A table with item columns names its `dress` (RQ-159): the KO item tables its
items resolve through and the client's robe exemptions; `columns` names the
hand-plug and part-slot columns, and `dress` gives each specialty's create
dress as KO's build draws it (1298 `005fd120`, 1264 `00439970`), each file
named as tools/assetc/ko_item_files.py does, checked by `build`.
`starting` (RQ-160, Q96 (b)) gives each specialty its starting items, groups
of specialties sharing a set, each set naming the weapon among its items that
the specialty can use, which the function `starting` checks against the
package's inventory, equipment and wear (features.json); or it is null and
every specialty starts with the package's `starting` items.
The realm owner's `realm-config.json` may name, under `create`, another `table`
(Q97), the `races` offered (Q94, default `content`), `reserved` words (Q99),
where a new character starts (`start`: KO's zone and map position, default the
package's spawn; Q96) and the `items` some specialties start with instead of
the package's (Q96: groups as `starting`'s, a group's items possibly none, as
KO's operator gives none, and its weapon possibly null). `starting` merges the
two and checks every set; `complete` cooks them into the `create` section
(create.bin version 2, RQ-154). Items the cook itself adds to the package's
starting items (`added`: the 2233 / 2145 additions' bow, arrows and armour,
tools/assetc/ko_chrplug_2145.py) join each of the package's `starting` sets, as
they join its `starting` items (RQ-178); a realm owner's set replaces the
package's and gets none of them.

`plan` checks both files and resolves the choice before any KO file is read;
`build` reads the table and texts and returns the manifest's `create` section
(tools/assetc/create.py's form), and checks the dress. This module knows KO's
create table layout only through the package's `columns` and `key`; no race or
specialty id is here.
"""
import hashlib
import math
import pathlib
import re

import create
import front_end_choice
import ko_item_files

SOURCE = "character-create.json"
KEYS = {"stats", "nation", "faces", "hairs", "races", "content", "player", "tables", "columns",
        "front_ends", "refusals", "name", "fixed", "models", "starting"}
# RQ-158: the forms a race's model ships in (each a list of races): `create`,
# the create screen's model (ko_front_end, N3FE version 24).
MODEL_KEYS = {"create"}
RACE_KEYS = {"race", "nation", "specialties", "looks"}
# A race's looks stem (UPC_DefaultLooks part names, ko_player.looks checks it).
LOOKS = re.compile(r"[a-z0-9_]{1,32}\Z")
TABLE_KEYS = {"values", "key", "texts", "dress"}
# RQ-159: a table's dress, or null for a table without item columns (1097's).
DRESS_KEYS = {"items", "extensions", "robe_exempt"}
COLUMN_KEYS = {"stats", "bonus", "plugs", "parts"}
MAX_SLOTS = 16
FIXED_KEYS = {"race", "specialty", "face", "hair", "points"}
# RQ-160: a group of specialties and the starting set they share.
STARTING_KEYS = {"specialties", "items", "weapon"}
MAX_STARTING = 64
# realm-config.json's `create`: the realm owner's choices (Q94, Q96, Q97, Q99).
CONFIG_KEYS = {"table", "races", "reserved", "start", "items"}
START_KEYS = {"zone", "position"}


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
        if type(race["looks"]) is not str or not LOOKS.match(race["looks"]):
            raise Refused("%s: race %r looks: 1 to 32 lower-case letters, digits or _" % (path, race["race"]))
    known = [race["race"] for race in races]
    ids(known, "%s races" % path)
    if not set(ids(r["content"], "%s content" % path)) <= set(known):
        raise Refused("%s: content names a race it does not list" % path)
    if type(r["player"]) is not int or r["player"] not in r["content"]:
        raise Refused("%s: player names a race without a player model (content)" % path)
    models = r["models"]
    if type(models) is not dict or set(models) != MODEL_KEYS:
        raise Refused("%s: models needs exactly %s" % (path, ", ".join(sorted(MODEL_KEYS))))
    if not set(ids(models["create"], "%s models.create" % path)) <= set(known):
        raise Refused("%s: models.create names a race it does not list" % path)
    if not set(r["content"]) <= set(models["create"]):
        raise Refused("%s: content names a race without a create model (models.create)" % path)
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
        d = t["dress"]
        if d is not None and (
                type(d) is not dict or set(d) != DRESS_KEYS or type(d["items"]) is not str or
                type(d["extensions"]) is not str or d["extensions"].count("{}") != 1 or
                front_end_choice.split(d["items"])[0] != front_end_choice.split(d["extensions"])[0] or
                type(d["robe_exempt"]) is not list or
                any(type(e) is not list or len(e) != 2 or any(type(v) is not int or not 0 <= v <= 4294 for v in e)
                    for e in d["robe_exempt"])):
            raise Refused("%s: table %r: dress is null or exactly %s: the items and extensions ({} the index) "
                          "tables of one input and [nation, item / 1000000] pairs" % (path, tid, ", ".join(sorted(DRESS_KEYS))))
    columns = r["columns"]
    slot_lists = [columns.get(k) for k in ("plugs", "parts")] if type(columns) is dict else []
    if type(columns) is not dict or set(columns) != COLUMN_KEYS or type(columns["stats"]) is not list or \
            len(columns["stats"]) != stats or \
            any(type(c) is not list or not 1 <= len(c) <= MAX_SLOTS for c in slot_lists) or \
            any(type(c) is not int or not 1 <= c <= 63 for c in columns["stats"] + [columns["bonus"]]) or \
            any(c is not None and (type(c) is not int or not 1 <= c <= 63) for s in slot_lists for c in s):
        raise Refused("%s: columns {stats: %d column numbers, bonus, plugs and parts: a column number or null "
                      "per slot}" % (path, stats))
    used = columns["stats"] + [columns["bonus"]] + [c for s in slot_lists for c in s if c is not None]
    if len(set(used)) != len(used):
        raise Refused("%s: columns names a column twice" % path)
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
    starting = r["starting"]
    if starting is not None:
        groups(starting, races, "%s: starting" % path, "%s starting" % path, every=True)
    return r


def groups(value, races, what, where, every):
    """Checks a list of starting groups (`starting`, or realm-config.json's
    `create.items` when not `every`): each exactly STARTING_KEYS, each
    specialty of the races in one group at most (in one exactly when `every`),
    1 to MAX_STARTING distinct [item, count] pairs (0 for a realm owner's
    group) and its weapon one of them (or null for a realm owner's group)."""
    if type(value) is not list or (every and not value) or \
            any(type(g) is not dict or set(g) != STARTING_KEYS for g in value):
        raise Refused("%s is %sa list of groups, each exactly %s"
                      % (what, "null or " if every else "", ", ".join(sorted(STARTING_KEYS))))
    least = 1 if every else 0
    given = []
    for g in value:
        given += ids(g["specialties"], "%s specialties" % where)
        items = g["items"]
        if type(items) is not list or not least <= len(items) <= MAX_STARTING or \
                any(type(i) is not list or len(i) != 2 or type(i[0]) is not str or not i[0] or
                    type(i[1]) is not int or not 1 <= i[1] <= 9999 for i in items) or \
                len({i[0] for i in items}) != len(items):
            raise Refused("%s %s: items, %d to %d distinct [item, count] pairs, count 1..9999"
                          % (what, g["specialties"], least, MAX_STARTING))
        if not (g["weapon"] is None and not every) and \
                (type(g["weapon"]) is not str or g["weapon"] not in [i[0] for i in items]):
            raise Refused("%s %s: weapon is one of its items%s" % (what, g["specialties"], "" if every else ", or null"))
    offered = {s for race in races for s in race["specialties"]}
    twice = sorted({s for s in given if given.count(s) > 1})
    missing = sorted(offered - set(given)) if every else []
    extra = sorted(set(given) - offered)
    if twice or missing or extra:
        raise Refused("%s names each specialty the races have %s (%s)" % (what, "once" if every else "at most once", "; ".join(
            how % ", ".join(map(str, v)) for how, v in (("twice: %s", twice), ("without a set: %s", missing),
                                                        ("no race has: %s", extra)) if v)))


def plan(game, client, config):
    """The create choice for front end `client` and realm-config.json's
    `config` ({} or its `create`), before any KO file is read: {rules, table
    (id), races (offered), reserved, start (None or {zone, position}), items
    (the realm owner's groups, [] by default)}, or None for a package without
    create rules. Refuses, naming the file to change, a malformed choice, a
    table the package lacks, a race without a player model and a fixed choice
    whose race is not offered. The start's zone and map are checked when the
    zone is cooked (`complete`), its items against the package's bag
    (`starting`)."""
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
    start = config.get("start")
    if start is not None and (
            type(start) is not dict or set(start) != START_KEYS or type(start["zone"]) is not int or
            not 1 <= start["zone"] <= 65535 or type(start["position"]) is not list or len(start["position"]) != 2 or
            any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in start["position"])):
        raise Refused("%s: create.start is exactly {zone, position}: KO's zone id and its map position [x, z] in "
                      "metres, as START_POSITION and the operator's CREATE_NEW_CHAR name them" % path)
    items = config.get("items", [])
    groups(items, r["races"], "%s: create.items" % path, "create.items", every=False)
    return dict(rules=r, table=table, races=races, reserved=sorted({w.lower() for w in reserved}),
                start=start, items=items)


def values(r, tid, assets):
    """The chosen table's bytes and its rows by id, each with the stat columns
    and, for a table with a dress, the item columns."""
    import ko_tbl
    table = r["tables"][tid]
    data = assets.get(table["values"])
    _, rows = ko_tbl.parse(ko_tbl.decrypt(data))
    columns = r["columns"]
    read = [0] + columns["stats"] + [columns["bonus"]]
    if table["dress"] is not None:
        read += [c for c in columns["plugs"] + columns["parts"] if c is not None]
    by_id = {}
    for row in rows:
        if len(row) <= max(read) or any(type(row[c]) is not int for c in read):
            raise Refused("create table %s (%s): a row without the %s columns" % (
                tid, table["values"], "stat and item" if table["dress"] is not None else "stat"))
        if row[0] in by_id:
            raise Refused("create table %s (%s): row %d twice" % (tid, table["values"], row[0]))
        by_id[row[0]] = row
    return data, by_id


def row_id(table, race, specialty):
    return race * table["key"]["race"] + specialty * table["key"]["specialty"]


def dress(chosen, assets, races=None):
    """Each specialty's create dress from `plan`'s choice and the front end's
    inputs: {race: {specialty: {parts, plugs}}} for `races` (default the races
    offered and those with a create model), or None for a table without item
    columns (KO draws the looks parts: 1097's SetChr `004359f0`).

    As KO's build (1298 `005fd120`, 1264 `00439970`; binary): each part slot's
    column holds an item, the slots in order; the face's slot (null) is the
    race's face, and an item of 0 leaves the slot the race's looks part (the
    helmet's slot its hair). A part is {slot, item, file}; a lower part under an
    upper that is a robe is {slot, item, file: null}, drawn bare (1298
    `00467d50` with `00462bd0`). Each hand plug's column holds an item for that
    hand, whatever hand its row names; a plug is {slot, item, kind (its Item_Org
    class, which puts a left-hand 60 on the shield joint: 1298 `00467b30`),
    file}. A file is named by ko_item_files with the specialty and read from
    the input of the table's items, its prefix kept. (1264 names a race's one
    set with the race's default class, 00439970; a name depends on the class
    only through the client's switch accepting it, which every specialty must,
    so a table keyed by race gives each specialty that set.) Refuses an item
    the items table lacks, an item whose form or slot is not its column's, and
    one that names no file or a file the input lacks."""
    r, tid = chosen["rules"], chosen["table"]
    table = r["tables"][tid]
    d = table["dress"]
    if d is None:
        return None
    if races is None:
        races = set(chosen["races"]) | set(r["models"]["create"])
    _, by_id = values(r, tid, assets)
    tree, rest = assets.split(d["items"])
    prefix = d["items"][:len(d["items"]) - len(rest)]

    def items(path, types):
        try:
            return ko_item_files.table(assets.get(path), types, path)
        except front_end_choice.Refused:
            raise
        except ValueError as error:
            raise Refused("create table %s dress: %s" % (tid, error))

    orgs = items(d["items"], ko_item_files.ORG_TYPES)
    exts = {}

    def ext(org):
        index = org[ko_item_files.ORG["extension"]]
        if index not in exts:
            exts[index] = items(d["extensions"].format(index), ko_item_files.EXT_TYPES)
        return exts[index]

    def resolve(where, item, race, specialty, want, slot):
        org = orgs.get(item // 1000 * 1000)
        if org is None:
            raise Refused("%s: item %d has no row %d in %s" % (where, item, item // 1000 * 1000, d["items"]))
        index = org[ko_item_files.ORG["extension"]]
        if index >= ko_item_files.EXTENSIONS:
            # 006157b0 / 005d2a80 index the extension tables with it for any item.
            raise Refused("%s: item %d names Item_Ext table %d: KO has tables 0..%d, and its name function reads "
                          "past them (006157b0, 005d2a80)" % (where, item, index, ko_item_files.EXTENSIONS - 1))
        kind = ko_item_files.form(org)
        if kind is None or kind[0] != want or (want == "part" and kind[1] != slot):
            raise Refused("%s: item %d is %s, not %s %d" % (
                where, item, "an icon" if kind is None else "%s %d" % kind, want, slot))
        row = ext(org).get(item % 1000) if want == "plug" else None
        try:
            name = ko_item_files.name(org, row, race, specialty)
        except ValueError as error:
            raise Refused("%s: %s" % (where, error))
        if not name:
            raise Refused("%s: item %d names no file (006157b0: its resource is 0, it is a plug without an "
                          "Item_Ext row, or its class is 11 or less)" % (where, item))
        if not tree.has(name):
            raise Refused("%s: item %d's file %s is not in the input" % (where, item, prefix + name))
        return org, prefix + name

    columns = r["columns"]
    out = {}
    for race in r["races"]:
        if race["race"] not in races:
            continue
        sets = {}
        for s in race["specialties"]:
            rid = row_id(table, race["race"], s)
            row = by_id.get(rid)
            if row is None:
                raise Refused("create table %s (%s): no row %d for race %d specialty %d"
                              % (tid, table["values"], rid, race["race"], s))
            where = "create table %s row %d (race %d specialty %d)" % (tid, rid, race["race"], s)
            parts, plugs, robe = [], [], False
            for slot, column in enumerate(columns["parts"]):
                if column is None:
                    continue
                item = row[column]
                if slot == ko_item_files.LOWER and robe:
                    parts.append(dict(slot=slot, item=item, file=None))
                    continue
                if item == 0:
                    continue
                org, name = resolve("%s column %d" % (where, column), item, race["race"], s, "part", slot)
                if slot == ko_item_files.UPPER:
                    robe = ko_item_files.robe(org, race["nation"], d["robe_exempt"])
                parts.append(dict(slot=slot, item=item, file=name))
            for slot, column in enumerate(columns["plugs"]):
                if column is None or row[column] == 0:
                    continue
                item = row[column]
                org, name = resolve("%s column %d" % (where, column), item, race["race"], s, "plug", slot)
                plugs.append(dict(slot=slot, item=item, kind=org[ko_item_files.ORG["kind"]], file=name))
            sets[s] = dict(parts=parts, plugs=plugs)
        out[race["race"]] = sets
    return out


def starting(chosen, manifest, added=()):
    """Each specialty's starting set (RQ-160, RQ-154, Q96 (b)): {specialty:
    {items: [[item, count], ...], weapon}}: the package's `starting`, each
    specialty a realm owner's `create.items` group names taking that group's
    instead; or None when neither names a set (every specialty starts with the
    package's `starting` items). `complete` cooks it into create.bin.

    `added` ([[item, count], ...]) are the starting items the cook adds to the
    package's bag beyond its source's (ko_bake's additions): each of the
    package's own sets carries them after its items, an item the set already
    names keeping the set's count (RQ-178), so Moradon's set (its source's
    `starting` items) still holds every starting item the cooked package
    grants. A realm owner's set does not.

    Checked against the package `manifest`'s inventory, equipment and wear
    (features.json and what the cook adds): each item is in the bag and not
    the progression's reward item, its count at most its stack limit, and a
    set fits the bag beside the progression's reward slots, as the inventory
    cook requires of the package's own `starting`. The weapon (a realm
    owner's may be null) is an equipment item that attacks (a wear item with
    attack slots) and that the package's player may wear, by the server's
    rule (server/src/equipment.rs `eligible`): its race 0 or the package's,
    its title and attributes at most the package's. (KO grants no items,
    CREATE_NEW_CHAR, local-asset; its items name the class that may wear them
    and their stat floors, content/character-create.md, "Starting items".)
    Refuses a set that does not."""
    r = chosen["rules"]
    def joined(g):
        named = {item for item, _ in g["items"]}
        return dict(g, items=[list(i) for i in g["items"]] + [list(i) for i in added if i[0] not in named])
    sets = [(SOURCE + " starting", joined(g)) for g in r["starting"] or []] + \
        [("%s create.items" % front_end_choice.CONFIG, g) for g in chosen.get("items", [])]
    if not sets:
        return None
    if any(k not in manifest for k in ("inventory", "equipment", "wear")):
        raise Refused("%s: starting needs the package's inventory, equipment and wear (features.json)" % SOURCE)
    inventory, equipment = manifest["inventory"], manifest["equipment"]
    bag = {i["id"]: i for i in inventory["items"]}
    gear = {i["id"]: i for i in equipment["items"]}
    attacks = {i["id"] for i in manifest["wear"]["items"] if i["attack_slots"]}
    rewards = manifest.get("gameplay", {}).get("slots", 0)
    reward = manifest.get("gameplay", {}).get("item")
    out = {}
    for source, g in sets:
        where = "%s %s" % (source, g["specialties"])
        for item, count in g["items"]:
            if item not in bag:
                raise Refused("%s: item %s is not in the package's inventory" % (where, item))
            if item == reward:
                raise Refused("%s: item %s is the progression's reward item, which no set may start with" % (where, item))
            if count > bag[item]["stack_limit"]:
                raise Refused("%s: item %s: %d over its stack limit %d" % (where, item, count, bag[item]["stack_limit"]))
        if len(g["items"]) >= inventory["capacity"] or len(g["items"]) + rewards > inventory["capacity"]:
            raise Refused("%s: %d stacks and %d reward slots do not fit the bag of %d"
                          % (where, len(g["items"]), rewards, inventory["capacity"]))
        if g["weapon"] is not None:
            weapon = gear.get(g["weapon"])
            if weapon is None or g["weapon"] not in attacks:
                raise Refused("%s: weapon %s is not an equipment item that attacks (equipment, wear attack_slots)"
                              % (where, g["weapon"]))
            if weapon["title"] > equipment["title"] or weapon["race"] not in (0, equipment["race"]) or \
                    any(need > base for need, base in zip(weapon["attributes"], equipment["attributes"])):
                raise Refused("%s: weapon %s: the package's player may not wear it (its race, title or attributes)"
                              % (where, g["weapon"]))
        for s in g["specialties"]:
            out[s] = dict(items=[list(i) for i in g["items"]], weapon=g["weapon"])
    return out


def complete(section, report, chosen, manifest, zone, extent, added=()):
    """Adds the realm owner's start and each specialty's starting items to the
    manifest's `create` section (`build`'s) and the start to its provenance
    `report` (RQ-154, Q96). The start's `zone` must be the package's zone
    (`zone`, KO's zone id: the realm is one zone) and its position on the map
    of `extent` metres a side; it is cooked as engine metres (KO's x and z
    from the map's corner, ko_start's rule: x - half, half - z), the server
    refusing a start off the ground. Each specialty the section's races offer
    gets its set from `starting` (the weapon is checked there, not cooked;
    `added` as `starting` takes it); without one it starts with the package's
    `starting` items."""
    start = chosen.get("start")
    if start is not None:
        path = "%s create.start" % front_end_choice.CONFIG
        if start["zone"] != zone:
            raise Refused("%s: zone %d is not the package's zone %d (the realm is one zone)" % (path, start["zone"], zone))
        x, z = start["position"]
        if not (0 <= x <= extent and 0 <= z <= extent):
            raise Refused("%s: position [%g, %g] leaves the %g m map" % (path, x, z, extent))
        half = extent / 2.0
        section["start"] = [float(x - half), float(half - z)]
        report["start"] = dict(zone=zone, position=[x, z], engine=section["start"])
    kits = starting(chosen, manifest, added)
    if kits is not None:
        # One kit per specialty, in the order the offered races first name it:
        # KO's races share specialty ids (the Tuarek's 104 is the Puri Tuarek's).
        offered = list(dict.fromkeys(s["specialty"] for race in section["races"] for s in race["specialties"]))
        section["items"] = [dict(specialty=s, items=kits[s]["items"]) for s in offered if s in kits]
    try:
        create.check(section)
    except ValueError as error:
        raise Refused("%s: %s" % (SOURCE, error))
    return section


def build(chosen, assets):
    """The manifest's `create` section and its provenance, from `plan`'s choice
    and the front end's inputs (`ko_front_end.Inputs`). Refuses a table whose
    rows name a race or specialty the package lacks, or that lacks a row the
    package's offered races need (Q97), and a dress `dress` refuses."""
    import ko_front_end
    r, tid = chosen["rules"], chosen["table"]
    table = r["tables"][tid]
    data, by_id = values(r, tid, assets)
    columns = r["columns"]
    known = {row_id(table, race["race"], s) for race in r["races"] for s in race["specialties"]}
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
            row = by_id.get(row_id(table, race["race"], s))
            if row is None:
                raise Refused("create table %s (%s): no row %d for race %d specialty %d"
                              % (tid, table["values"], row_id(table, race["race"], s), race["race"], s))
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
    # RQ-159: every dress the create screen and the select hall will draw
    # (RQ-004, RQ-005) resolves to files in the inputs; nothing is cooked from
    # it yet, so the section and the provenance are as before.
    dress(chosen, assets)
    texts = assets.get(table["texts"])
    report = dict(table=tid, values=table["values"], values_sha256=hashlib.sha256(data).hexdigest(),
                  texts=table["texts"], texts_sha256=hashlib.sha256(texts).hexdigest(), races=chosen["races"])
    return section, report
