"""KO NPC templates from the operator's K_MONSTER and K_NPC rows (PQ-251, D-164).

`zone_templates` builds one N3N3 template (tools/assetc/npc.py,
`reference_templates_v3`; with its `scale` it cooks as N3N4, PQ-272) for every template a zone's used K_NPCPOS rows name,
read through `ko_tables` (PQ-054: checked, canonical, never committed). Each
column is mapped as the supplied AI server uses it (`AI Server-official.exe`,
binary unless noted; record: docs/implementation/evidence/pq-251-npc-reference-stats.md):

* The loads `00437fb4` (K_MONSTER) and `00438479` (K_NPC) copy a row into a
  0x98-byte template, and the spawn load `0043893e` copies the template into
  each NPC's own record (`[NPC+0x4f4]`), which every later path reads.
* strName (record `+0x02`, sent by the NPC info record `0042214c`): n3e names a
  template by a package rule ID, `<game>:monster/<sSid>-<slug>` or
  `<game>:npc/<sSid>-<slug>`, unique because each table's `sSid` is
  (`ko_tables` refuses a repeat). KO's text is not a display label in n3e yet.
* sPid (record `+0x22`, sent after the id by `0042214c`; the client's looks key,
  PQ-176): `<game>:looks/<sPid>`. PQ-253/PQ-254 give each key its model.
* iHpPoint (record `+0x44` and the NPC's health `+0x4f8`; `0042214c` sends both,
  regeneration `004248e5` heals `+0x44` / 20): `health`.
* sLevel (record `+0x38`; `0042214c` sends it as one byte, `0040a7aa`; read by
  the kill reward `004209da`, `0042670d` and the drop roll `00423e5e`): `level`.
* sAttackDelay (record `+0x54`; the attack routine `0041de51` returns it as the
  next delay, which the fighting state `004183c2` stores at `+0x518`, ms):
  `attack_ticks`, whole 50 ms ticks rounded up, so never faster than KO.
* bySpeed2 (record `+0x5c` = bySpeed2 x 1500 x 0.001, `00438d54`-`00438d91`;
  chase and path steps take it every 1,500 ms, the constant copied to `+0x56`,
  `004184cb`): metres per second, `speed`. 0 never moves. bySpeed1 (`+0x58`) is
  read only by wander (`00419fd9`), which n3e lacks (PQ-070).
* bySearchRange (record `+0x84`; the scan `0041c21e` takes players whose 3-D
  distance from the NPC is at most it): `search_range` (n3e measures the same).
* byTracingRange (record `+0x86`; the path limit `0041d5d1` for a target in the
  damage list): `tracing_range`, n3e's home leash (the D-106 adaptation).
* sSize (template `+0x28`, record `+0x24` from `00438c42`; `0042214c` sends it
  as the fourth short at `004221d5`, Ebenezer relays it into the NPC-in record
  after the looks key, the type byte and a u32, and the client's NPC-in
  multiplies it by 0.01 into the character's scale, `005cdd82`-`005cdda9`;
  PQ-272, D-179): `scale`, the drawn size in percent (1-1000).
* byAttackRange (record `+0x85`) with the radius r = sSize x 0.01 x sBulk x 0.01
  (record `+0x80`, `00438e58`-`00438e84`): the band routine `0041d266` takes the
  horizontal distance d to the target and needs trunc(d - r) <= byAttackRange;
  a melee NPC (byDirectAttack 0) then strikes only while d - r < r + 3.0, a
  byDirectAttack 1 NPC while d - r < 30.0, and a byDirectAttack 2 NPC anywhere
  in the band (`0041de51`, `0041e628`). So `attack_range` is the distance below
  which it strikes: min(2r + 3, A + r + 1), min(r + 30, A + r + 1) or A + r + 1.
* byActType (record `+0x31`; `0042476d` clears the aggressive flag `+0x508` for
  1-4 and leaves it set otherwise, default 1 from `00417873`; the scan
  `0041c21e` then takes only damaged-by players): `acquisition` passive for
  1-4, else aggressive. A spawn row's ActType >= 100 picks the K_NPC table and
  stores ActType - 100 as the spawn's own act type (`0043893e`, path types 2
  and 3), not the template's.
* byGroup (record `+0x30`): the scan and the attack skip a player whose `+0x66`
  equals it (`0041c21e`, `0041de51`; reading `+0x66` as the nation is the
  source name). n3e has no nation; a package that seats its players in one
  nation (`ko_start.PACKAGE_NATION`, 1 Karus, 2 El Morad: `004c6523`) passes it
  as `nation`, and a template of that group is passive. KO also never
  retaliates against or is attacked by its own nation; that is PQ-258.
* sStandtime (record `+0x60`): the standing delay (`00418fb6`, `0041817d`,
  `00428897`, `004184cb`) between wander moves; acquisition still runs during
  it (`0042b86c`). It joins the template with wander (PQ-070); not carried.

Combat and XP (PQ-252, D-165; docs/implementation/evidence/pq-252-npc-reference-combat.md).
The loads put sAc, sHitRate, sEvadeRate and sDamage at template `+0x54`..`+0x5a`
and iExp at `+0x44` (bindings `0041737b`), and the spawn load copies them to
record `+0x4c`, `+0x4e`, `+0x50`, `+0x52` and `+0x3c`:

* sDamage (record `+0x52`): the NPC's strike on a user (`0041f535`, from the
  attack routine `0041de51`) is X = sDamage x 200 / (user `+0x94` + 240), a
  roll of 0.85 X + 0.3 rand(0, X) (x3/2 on the highest grade), capped at
  2.6 x sDamage: n3e's N3D1 NPC side, `attack`. It is also `damage`, the
  fixed strike of a package without N3D1. 0 never damages. Rows above 10,000
  are refused: that is past n3e's N3D1 attack bound; KO's short result wraps
  only above about 22,800 (defence 0, PQ-260).
* sHitRate (record `+0x4e`): divided by user `+0x90`, it picks the grade row
  (`004235aa`): `accuracy`. (User `+0x94`, `+0x90`, `+0x8a`, `+0x8c` are read
  as defence, evasion, attack and hit rate by their use here: inference.)
* sAc (record `+0x4c`): what a user's strike divides by (`00443a34`,
  reached from the dispatcher `00404cc6` case 0x33 through `00405f1c` and
  `004430d8`): `defense`.
* sEvadeRate (record `+0x50`): the divisor of user `+0x8c` there
  (`00444164`): `evasion`.
* iExp (record `+0x3c`): the base XP the kill reward `004209da` shares by
  damage dealt: `xp`; 0 awards nothing.
"""
import math
import re
import sys

import ko_tables

TICK_MS = 50  # n3e simulation tick
# n3e template bounds (npc.py TEMPLATE_INTEGERS / TEMPLATE_FLOATS) the rows must meet.
MAX_XP = 50000000
MAX_ATTACK = 10000  # n3e's N3D1 attack bound (KO's short result wraps only above about 22,800, PQ-260)
MAX_STAT = 32767  # sAc, sHitRate, sEvadeRate are shorts
MAX_HEALTH = 2000000
MAX_LEVEL = 255
MAX_SPEED = 12
MAX_RANGE = 64.0
MAX_TEMPLATES = 256
MAX_SCALE = 1000  # n3e's template scale bound (npc.py SCALE), percent
TABLE_PREFIX = {"K_MONSTER": "monster", "K_NPC": "npc"}


def slug(text):
    """Lower-case ASCII words of a KO name joined by '-'; '' for none."""
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def rule_name(game, table, row):
    tail = slug(row["strName"])
    return "%s:%s/%d%s" % (game, TABLE_PREFIX[table], row["sSid"], "-" + tail if tail else "")


def radius(row):
    """Record +0x80 (0043893e): sSize x 0.01 x sBulk x 0.01, as f32 products."""
    return (row["sSize"] * 0.01) * (row["sBulk"] * 0.01)


def strike_distance(row):
    """Horizontal distance below which 0041d266 lets the NPC strike."""
    r, band = radius(row), row["byAttackRange"] + radius(row) + 1
    if row["byDirectAttack"] == 0:
        return min(2 * r + 3, band)
    if row["byDirectAttack"] == 1:
        return min(r + 30, band)
    return band


def template(table, row, game, nation=None, drawn_scale=True):
    """The N3N3 template for one K_MONSTER or K_NPC row (a ko_tables dict).
    `drawn_scale` False leaves out `scale` (sSize, still bounds-checked) for a
    package without a looks table, which cannot carry one (PQ-272)."""
    where = "%s sSid %d" % (table, row["sSid"])

    def need(ok, what):
        if not ok:
            raise ValueError("%s: %s" % (where, what))

    need(1 <= row["iHpPoint"] <= MAX_HEALTH, "iHpPoint %d outside 1..%d" % (row["iHpPoint"], MAX_HEALTH))
    need(1 <= row["sLevel"] <= MAX_LEVEL, "sLevel %d outside 1..%d" % (row["sLevel"], MAX_LEVEL))
    need(row["sPid"] >= 0, "sPid %d is negative" % row["sPid"])
    need(1 <= row["sAttackDelay"] <= 1200 * TICK_MS, "sAttackDelay %d outside 1..60000 ms" % row["sAttackDelay"])
    need(row["bySpeed2"] <= MAX_SPEED, "bySpeed2 %d above %d" % (row["bySpeed2"], MAX_SPEED))
    need(row["bySearchRange"] >= 1 and row["byTracingRange"] >= 1, "search or tracing range 0")
    need(row["bySearchRange"] <= row["byTracingRange"],
         "bySearchRange %d beyond byTracingRange %d" % (row["bySearchRange"], row["byTracingRange"]))
    need(row["byTracingRange"] <= MAX_RANGE, "byTracingRange %d above %g" % (row["byTracingRange"], MAX_RANGE))
    need(row["byDirectAttack"] in (0, 1, 2), "byDirectAttack %d" % row["byDirectAttack"])
    need(0 <= row["iExp"] <= MAX_XP, "iExp %d outside 0..%d" % (row["iExp"], MAX_XP))
    need(0 <= row["sDamage"] <= MAX_ATTACK, "sDamage %d outside 0..%d" % (row["sDamage"], MAX_ATTACK))
    for column in ("sAc", "sHitRate", "sEvadeRate"):
        need(0 <= row[column] <= MAX_STAT, "%s %d outside 0..%d" % (column, row[column], MAX_STAT))
    need(1 <= row["sSize"] <= MAX_SCALE, "sSize %d outside 1..%d" % (row["sSize"], MAX_SCALE))
    reach = strike_distance(row)
    need(0.05 <= reach <= MAX_RANGE, "attack distance %.2f outside 0.05..%g" % (reach, MAX_RANGE))
    passive = 1 <= row["byActType"] <= 4 or (nation is not None and row["byGroup"] == nation)
    out = {
        "name": rule_name(game, table, row),
        "looks": "%s:looks/%d" % (game, row["sPid"]),
        "acquisition": "passive" if passive else "aggressive",
        "health": row["iHpPoint"],
        "level": row["sLevel"],
        "attack_ticks": -(-row["sAttackDelay"] // TICK_MS),
        "speed": row["bySpeed2"],
        # f32-exact: the readers compare the cooked f32 with these bounds.
        "attack_range": round(reach, 4),
        "search_range": row["bySearchRange"],
        "tracing_range": row["byTracingRange"],
    }
    if drawn_scale:
        out["scale"] = row["sSize"]
    out.update(xp=row["iExp"], damage=row["sDamage"], attack=row["sDamage"], defense=row["sAc"],
               accuracy=row["sHitRate"], evasion=row["sEvadeRate"])
    return out


def zone_templates(tables, zone, game, nation=None, drawn_scale=True):
    """Templates for one zone: (templates, spawns).

    `tables` maps K_MONSTER, K_NPC and K_NPCPOS to `ko_tables.load` results.
    `templates` is one N3N3
    template per distinct (table, sSid) the zone's used spawn rows name,
    ordered by table (K_MONSTER first) and sSid; `spawns` is each used spawn
    row (not skipped by 0043893e, NumNPC > 0) of the zone, in canonical order,
    with its template name: [(row dict, name)].
    """
    ko_tables.check_spawns(tables["K_NPCPOS"], tables["K_MONSTER"], tables["K_NPC"])
    rows = {name: {r["sSid"]: r for r in ko_tables.rows_as_dicts(tables[name])} for name in TABLE_PREFIX}
    used, spawns = {}, []
    for spawn in ko_tables.rows_as_dicts(tables["K_NPCPOS"]):
        if spawn["ZoneID"] != zone or ko_tables.spawn_skipped(spawn) or spawn["NumNPC"] == 0:
            continue
        table, _ = ko_tables.spawn_template(spawn)
        key = (list(TABLE_PREFIX).index(table), spawn["NpcID"])
        if key not in used:
            used[key] = template(table, rows[table][spawn["NpcID"]], game, nation, drawn_scale)
        spawns.append((spawn, used[key]["name"]))
    if not spawns:
        raise ValueError("K_NPCPOS has no used row for zone %d" % zone)
    if len(used) > MAX_TEMPLATES:
        raise ValueError("zone %d uses %d templates (bound %d)" % (zone, len(used), MAX_TEMPLATES))
    return [used[k] for k in sorted(used)], spawns


def main(argv):
    import argparse
    import hashlib
    import json
    parser = argparse.ArgumentParser(description="Build a zone's N3N3 NPC templates from the operator's "
                                     "K_MONSTER, K_NPC and K_NPCPOS exports (PQ-251); prints a summary only.")
    parser.add_argument("zone", type=int)
    parser.add_argument("--export", default=str(ko_tables.EXPORT))
    parser.add_argument("--game", default="ko")
    parser.add_argument("--nation", type=int, choices=(1, 2))
    args = parser.parse_args(argv)
    try:
        tables = {}
        for name in ko_tables.TABLES:
            tables[name] = ko_tables.load(name, args.export)
            if tables[name] is None:
                raise ValueError("%s/%s.json is missing" % (args.export, name))
        templates, spawns = zone_templates(tables, args.zone, args.game, args.nation)
    except ValueError as error:
        print("REFUSED " + str(error), file=sys.stderr)
        return 2
    text = json.dumps(templates, sort_keys=True, separators=(",", ":"))
    span = lambda k: "%s..%s" % (min(t[k] for t in templates), max(t[k] for t in templates))
    print("zone %d: %d templates (%d K_MONSTER, %d K_NPC), %d spawn rows, %d NPCs; sha256 %s" % (
        args.zone, len(templates), sum(":monster/" in t["name"] for t in templates),
        sum(":npc/" in t["name"] for t in templates), len(spawns), sum(s["NumNPC"] for s, _ in spawns),
        hashlib.sha256(text.encode()).hexdigest()))
    for key in ("health", "level", "attack_ticks", "speed", "attack_range", "search_range", "tracing_range",
                "xp", "attack", "defense", "accuracy", "evasion"):
        print("  %s %s" % (key, span(key)))
    print("  passive %d, aggressive %d" % (sum(t["acquisition"] == "passive" for t in templates),
                                           sum(t["acquisition"] == "aggressive" for t in templates)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
