"""PQ-251, PQ-252: a zone's N3N3 NPC templates from K_MONSTER and K_NPC (tools/assetc/ko_npc.py).

Synthetic rows only are committed; they are original values, not reference rows.
Each mapped column is checked against the binary reading in ko_npc's docstring
(records: docs/implementation/evidence/pq-251-npc-reference-stats.md and
pq-252-npc-reference-combat.md), every
template the cook writes must pass the N3N3 cooker (tools/assetc/npc.py), and
rows the n3e bounds cannot carry are refused by name. With the operator's own
export (`ko_tables.EXPORT`, never committed; SKIP without it) zones 1 and 2 are
cooked too, and when its digests are the pinned OpenKO v0.1.2 ones their counts
and ranges are checked. PQ-288: the committed Moradon worm row's `sSize` is
its template scale and the Moradon cook's drawn factor, and with the pinned
export the committed row equals the export's row. `make test` runs this file. (Named apart from
`tools/assetc/ko_npc.py`, so `import ko_npc` never finds this file.)
"""
import copy, json, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path("tools/assetc").resolve()))
import ko_npc
import ko_tables
import npc

B = Path("build/pq251-test")
shutil.rmtree(B, ignore_errors=True)
B.mkdir(parents=True)


def row(sid, **kw):
    out = {c: 1 for c, _, _ in ko_tables.COLUMNS["K_MONSTER"]}
    out.update(sSid=sid, strName="Sample %d" % sid, sPid=sid + 1, sLevel=30, iHpPoint=500, sAttackDelay=1500,
               bySpeed1=1, bySpeed2=3, sStandtime=1000, byAttackRange=5, bySearchRange=6, byTracingRange=30,
               byActType=5, byGroup=0, sSize=100, sBulk=100, byDirectAttack=0,
               iExp=10, sDamage=3, sAtk=7, sAc=1, sHitRate=50, sEvadeRate=20)
    out.update(kw)
    return out


def spawn(npc_id, act=1, zone=7, **kw):
    out = {c: 0 for c, _, _ in ko_tables.COLUMNS["K_NPCPOS"]}
    del out["path"]
    out.update(ZoneID=zone, NpcID=npc_id, ActType=act, LeftX=10, TopZ=20, RightX=30, BottomZ=40, NumNPC=2, RegTime=30)
    out.update(kw)
    return out


def load(monsters, npcs, spawns, name="ok"):
    folder = B / name
    folder.mkdir(parents=True, exist_ok=True)
    for table, rows in (("K_MONSTER", monsters), ("K_NPC", npcs), ("K_NPCPOS", spawns)):
        (folder / (table + ".json")).write_text(json.dumps(rows))
    return {t: ko_tables.load(t, folder) for t in ko_tables.TABLES}


MONSTERS = [
    # A homeland-sized boss: level 110, 150,000 HP, 9 m/s, 25 m search, 60 m tracing.
    row(10, strName="Sample Boss", sLevel=110, iHpPoint=150000, bySpeed1=2, bySpeed2=9, bySearchRange=25,
        byTracingRange=60, sAttackDelay=1510, sPid=701),
    # PQ-252: the largest reference iExp, the largest attack n3e takes, a
    # short's largest defence and rates; then the zero row (camp gate shape).
    row(70, iExp=39438375, sDamage=10000, sAc=32767, sHitRate=32767, sEvadeRate=32767),
    row(80, iExp=0, sDamage=0, sAc=0, sHitRate=0, sEvadeRate=0),
    # Passive (act 1), radius 1.5 x 2.0 = 3 m: strikes below min(2r + 3, A + r + 1) = 7.
    row(20, strName="Hill  [Runt] ", byActType=1, sSize=150, sBulk=200, byAttackRange=3, sPid=702),
    # byDirectAttack 1 strikes below min(r + 30, A + r + 1); 2 below A + r + 1.
    row(30, strName=None, byDirectAttack=1, byAttackRange=40, bySearchRange=10, byTracingRange=40),
    row(40, byDirectAttack=2, byAttackRange=10, byActType=4),
    row(50, byActType=6),  # 6 keeps the default aggressive flag (00417873)
    row(60),  # used only by another zone
]
NPCS = [
    row(400, strName="Guard", byActType=7, byGroup=1, iHpPoint=10000, sLevel=60, bySpeed2=7, sPid=21000),
    row(500, strName="Camp Gate", byActType=0, byGroup=2, bySpeed1=0, bySpeed2=0, sPid=30100),
]
SPAWNS = [spawn(10), spawn(20), spawn(10, NumNPC=1), spawn(30), spawn(40), spawn(50), spawn(70), spawn(80),
          spawn(400, act=101, NumNPC=3), spawn(500, act=100, NumNPC=1),
          spawn(60, zone=8), spawn(20, NumNPC=0), spawn(40, SpecialType=7, TrapNumber=2)]
tables = load(MONSTERS, NPCS, SPAWNS)
templates, spawns = ko_npc.zone_templates(tables, 7, "demo", nation=1)
by = {t["name"]: t for t in templates}
names = ["demo:monster/10-sample-boss", "demo:monster/20-hill-runt", "demo:monster/30", "demo:monster/40-sample-40",
         "demo:monster/50-sample-50", "demo:npc/400-guard", "demo:npc/500-camp-gate"]
extremes = ["demo:monster/70-sample-70", "demo:monster/80-sample-80"]
assert [t["name"] for t in templates] == names[:5] + extremes + names[5:], [t["name"] for t in templates]
boss = by[names[0]]
# Combat (PQ-252): iExp -> xp; sDamage -> damage and attack (0041f535); sAc ->
# defense (00443a34); sHitRate -> accuracy (004235aa); sEvadeRate -> evasion
# (00444164). sAtk (record +0x4a) is read by neither strike and not carried.
assert boss == dict(name=names[0], looks="demo:looks/701", acquisition="aggressive", health=150000, level=110,
                    attack_ticks=31, speed=9, attack_range=5.0, search_range=25, tracing_range=60,
                    xp=10, damage=3, attack=3, defense=1, accuracy=50, evasion=20, scale=100), boss
assert [(by[n]["xp"], by[n]["damage"], by[n]["attack"], by[n]["defense"], by[n]["accuracy"], by[n]["evasion"])
        for n in extremes] == [(39438375, 10000, 10000, 32767, 32767, 32767), (0, 0, 0, 0, 0, 0)], extremes
assert (by[names[1]]["acquisition"], by[names[1]]["attack_range"]) == ("passive", 7.0)
# PQ-272 (D-179): sSize (template +0x28, record +0x24, sent by 004221d5 and
# multiplied by 0.01 in the client's NPC-in 005cdd82) is the drawn scale.
assert by[names[1]]["scale"] == 150 and {t["scale"] for t in templates} == {100, 150}
# A package without a looks table cannot carry the scale: the cook leaves it out.
bare = ko_npc.zone_templates(tables, 7, "demo", nation=1, drawn_scale=False)[0]
assert all("scale" not in t for t in bare) and [dict(t, scale=s["scale"]) for t, s in zip(bare, templates)] == templates
assert by[names[2]]["attack_range"] == 31.0 and by[names[3]]["attack_range"] == 12.0
assert [by[n]["acquisition"] for n in names[3:]] == ["passive", "aggressive", "passive", "aggressive"]
# The guard's group is the package nation (1): passive. The gate (group 2,
# speed 0) stays aggressive and never moves; without a nation the guard is too.
assert (by[names[6]]["speed"], by[names[6]]["looks"]) == (0, "demo:looks/30100")
alone = {t["name"]: t for t in ko_npc.zone_templates(tables, 7, "demo")[0]}
assert alone[names[5]]["acquisition"] == "aggressive"
assert {t["name"]: t["acquisition"] for t in ko_npc.zone_templates(tables, 7, "demo", nation=2)[0]}[names[6]] == "passive"
# Used spawn rows only, canonical order, each naming its template; zone 8 and the
# skipped and empty rows are not used.
assert sorted(n for _, n in spawns) == sorted([names[0], names[0], names[1], names[2], names[3], names[4],
                                               names[5], names[6]] + extremes), spawns
assert sum(s["NumNPC"] for s, _ in spawns) == 2 + 1 + 2 + 2 + 2 + 2 + 2 + 2 + 3 + 1
assert all(s["ZoneID"] == 7 and s["NumNPC"] > 0 and not ko_tables.spawn_skipped(s) for s, _ in spawns)
assert [t["name"] for t in ko_npc.zone_templates(tables, 8, "demo")[0]] == ["demo:monster/60-sample-60"]
# Every template cooks as N3N3, one slot per spawn member.
slots = [dict(area=[0, 0, 0, 0], respawn_ticks=600, template=n) for s, n in spawns for _ in range(s["NumNPC"])]
policy = dict(model="reference_templates_v3", scan_ticks=5, acquire_ticks=5, stuck_ticks=40, chase_ticks=200,
              return_ticks=200, recovery_ticks=20, renew_on_hit=True, return_heal=False, retaliate_returning=True,
              return_speed_percent=200, regen_interval_ticks=200, regen_divisor=20, spawn_tries=500,
              templates=templates, slots=slots)
assert npc.cook(policy, [[0, 0]] * len(slots), "demo")[:4] == b"N3N4"
assert npc.cook(dict(policy, templates=bare), [[0, 0]] * len(slots), "demo")[:4] == b"N3N3"
print("PASS KO templates: one N3N4 template per used K_MONSTER / K_NPC row (name, looks key, health, level, "
      "attack delay, run speed, strike distance, search and tracing ranges, acquisition; iExp, sDamage, sAc, "
      "sHitRate, sEvadeRate from 0 to 39,438,375 / 10,000 / 32,767; sSize as the drawn scale); every one cooks")


def refused(phrase, monsters=None, npcs=None, spawns=None, zone=7):
    t = load(monsters or MONSTERS, npcs or NPCS, spawns or SPAWNS, "refused")
    try:
        ko_npc.zone_templates(t, zone, "demo")
    except ValueError as error:
        assert phrase in str(error), (phrase, str(error))
        return
    raise AssertionError("accepted: " + phrase)


def boss_with(**kw):
    out = copy.deepcopy(MONSTERS)
    out[0].update(kw)
    return out


for kw, phrase in [(dict(iHpPoint=0), "iHpPoint 0"), (dict(iHpPoint=2000001), "iHpPoint 2000001"),
                   (dict(sLevel=0), "sLevel 0"), (dict(sLevel=256), "sLevel 256"), (dict(sPid=-1), "sPid -1"),
                   (dict(sAttackDelay=0), "sAttackDelay 0"), (dict(bySpeed2=13), "bySpeed2 13"),
                   (dict(bySearchRange=61), "beyond byTracingRange"), (dict(byTracingRange=65), "byTracingRange 65"),
                   (dict(bySearchRange=0), "range 0"), (dict(byDirectAttack=3), "byDirectAttack 3"),
                   # radius 5 x 10 = 50 m: strikes below min(103, 71) = 71, past 64.
                   (dict(sSize=500, sBulk=1000, byAttackRange=20), "attack distance 71.00"),
                   # PQ-252: iExp past 50,000,000, sDamage past n3e's N3D1
                   # attack bound of 10,000, negative shorts.
                   (dict(iExp=50000001), "iExp 50000001"), (dict(iExp=-1), "iExp -1"),
                   (dict(sDamage=10001), "sDamage 10001"), (dict(sDamage=-1), "sDamage -1"),
                   (dict(sAc=-1), "sAc -1"), (dict(sHitRate=-1), "sHitRate -1"), (dict(sEvadeRate=-1), "sEvadeRate -1"),
                   # PQ-272: sSize outside n3e's scale bound (1-1000 %).
                   (dict(sSize=0), "sSize 0"), (dict(sSize=1001), "sSize 1001"), (dict(sSize=-5), "sSize -5")]:
    refused(phrase, monsters=boss_with(**kw))
refused("no used row for zone 9", zone=9)
refused("has no K_NPC template", spawns=SPAWNS + [spawn(999, act=100)])
many = [row(1000 + i) for i in range(248)]  # 9 + 248 = 257
refused("uses 257 templates", monsters=MONSTERS + many, spawns=SPAWNS + [spawn(r["sSid"]) for r in many])
print("PASS KO templates: rows outside the n3e bounds (health, level, looks key, attack delay, speed, ranges, "
      "strike distance, iExp, sDamage, sAc, sHitRate, sEvadeRate, sSize), a missing template and more than 256 templates "
      "are refused by name")

# The Moradon worm (games/moradon/ko-reference.json, committed adopted columns;
# D-106) cooks to the values tools/assetc/moradon_features.py applies to it:
# health, attack interval, run speed, search and tracing ranges, passivity.
worm = json.loads(Path("games/moradon/ko-reference.json").read_text())
m = worm["monster"]
worm_tables = load([row(m["sSid"], **{k: v for k, v in m.items() if k != "sSid"})], NPCS,
                   [spawn(m["sSid"], zone=21, NumNPC=s["NumNPC"]) for s in worm["spawns"]], "worm")
(w,), _ = ko_npc.zone_templates(worm_tables, 21, "moradon")
assert (w["health"], w["attack_ticks"], w["speed"], w["search_range"], w["tracing_range"], w["acquisition"],
        w["level"], w["looks"]) == (m["iHpPoint"], m["sAttackDelay"] // 50, m["bySpeed2"], m["bySearchRange"],
                                    m["byTracingRange"], "passive", m["sLevel"], "moradon:looks/700"), w
print("PASS KO templates: the committed Moradon worm row cooks to the mapping moradon_features.py applies "
      "(7 HP, 40-tick attacks, 3 m/s, 3 m search, 40 m tracing, passive)")

# PQ-288: the worm's sSize (row 750: 120) is the template's drawn scale and the
# factor the Moradon cook draws its untemplated NPC set at (the clip scenes'
# instance scale and the NPC name height); a row the n3e bound (1-1000 %)
# cannot carry, or a missing or non-integer sSize, is refused by name.
import moradon_features
assert w["scale"] == m["sSize"] == 120 and moradon_features.drawn_scale() == m["sSize"] / 100 == 1.2, (w, m)
for bad in (0, 1001, -5, 1.5, "120", None, True):
    try:
        moradon_features.drawn_scale(dict(m, sSize=bad))
    except ValueError as error:
        assert "worm sSize" in str(error), error
    else:
        raise AssertionError("worm sSize %r accepted" % (bad,))
try:
    moradon_features.drawn_scale({k: v for k, v in m.items() if k != "sSize"})
except ValueError as error:
    assert "worm sSize None" in str(error), error
else:
    raise AssertionError("a worm row without sSize accepted")
assert moradon_features.drawn_scale(dict(m, sSize=1)) == .01 and moradon_features.drawn_scale(dict(m, sSize=1000)) == 10
print("PASS KO templates: the committed Moradon worm's sSize 120 is its template scale and the Moradon cook's "
      "drawn factor 1.2; sSize 0, 1001, -5, 1.5, '120', null, true or missing is refused")

# ---------------------------------------------------------------------------
# The operator's own export (never committed). Pinned: OpenKO v0.1.2, as
# tests/ko_tables_import.py pins it.
PINNED = {"K_MONSTER": "576fa0944adf750192af08e35166c0623df408eeb3ab55b7eacd549805ed2310",
          "K_NPC": "e293e09652303d49c7808824887248f56276bb5bd2f6140661a71e79fbc94c28",
          "K_NPCPOS": "d4487f5e905ec15ee6f2e5372c4110fc3aafcd9310b5002f181f0f4116d6278c"}
if not all((ko_tables.EXPORT / (t + ".json")).is_file() for t in ko_tables.TABLES):
    print("SKIP KO templates, operator export: %s lacks K_MONSTER, K_NPC or K_NPCPOS" % ko_tables.EXPORT)
else:
    real = {t: ko_tables.load(t) for t in ko_tables.TABLES}
    found = {}
    for zone, nation in ((1, 1), (2, 2)):
        zone_templates, zone_spawns = ko_npc.zone_templates(real, zone, "ko", nation)
        members = sum(s["NumNPC"] for s, _ in zone_spawns)
        slots = [dict(area=[0, 0, 0, 0], respawn_ticks=600, template=n) for s, n in zone_spawns
                 for _ in range(s["NumNPC"])]
        assert npc.cook(dict(policy, templates=zone_templates, slots=slots), [[0, 0]] * members, "ko")[:4] == b"N3N4"
        span = lambda k: (min(t[k] for t in zone_templates), max(t[k] for t in zone_templates))
        found[zone] = (len(zone_templates), sum(":npc/" in t["name"] for t in zone_templates), len(zone_spawns),
                       members, span("level"), span("health"), span("speed"), span("xp"), span("attack"),
                       span("defense"), span("accuracy"), span("evasion"), span("scale"),
                       sum(t["scale"] != 100 for t in zone_templates))
    if any(real[t]["digest"] != PINNED[t] for t in ko_tables.TABLES):
        print("SKIP KO templates, pinned counts: the export is not the pinned OpenKO v0.1.2 one (it cooks: %r)" % found)
    else:
        # PQ-272: drawn scale 55-200 %, 47 of the 108 templates not at 100 %.
        combat = ((0, 460150), (0, 5000), (126, 20000), (16, 497), (10, 1218), (55, 200), 47)
        assert found == {1: (108, 38, 321, 1238, (22, 110), (318, 150000), (0, 9), *combat),
                         2: (108, 38, 322, 1233, (22, 110), (318, 150000), (0, 9), *combat)}, found
        print("PASS KO templates, operator export: the pinned OpenKO v0.1.2 zones 1 and 2 cook 108 templates each "
              "(70 K_MONSTER, 38 K_NPC; levels 22-110, health 318-150,000, speed 0-9 m/s; XP 0-460,150, attack "
              "0-5,000, defence 126-20,000, hit rate 16-497, evasion 10-1,218; drawn scale 55-200 %, 47 templates not at "
              "100 %) for 1,238 and 1,233 NPCs, and every template passes the N3N4 cooker")
        # PQ-288: the committed worm row (games/moradon/ko-reference.json) is
        # the pinned export's K_MONSTER row 750 in every column it carries,
        # sSize included.
        exported = next(r for r in ko_tables.rows_as_dicts(real["K_MONSTER"]) if r["sSid"] == m["sSid"])
        assert all(exported[k] == v for k, v in m.items()), {k: (v, exported[k]) for k, v in m.items()}
        print("PASS KO templates, operator export: the committed Moradon worm row is the pinned export's K_MONSTER "
              "row %d in its %d columns (sSize %d)" % (m["sSid"], len(m), exported["sSize"]))
