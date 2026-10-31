"""PQ-252: KO reference combat and XP cooked into N3N3 templates (tools/assetc/ko_npc.py), live.

The package is the PQ-251 fixture (tests/npc_reference_stats_live.py: the PQ-249
engine 37 package on a flat 256 m heightfield, players seated in nation 1) with
two templates cooked from synthetic K_MONSTER and K_NPC rows (original values,
not reference rows), each column mapped as the AI server reads it:

* a "brute" K_MONSTER row: level 110, aggressive, sDamage 6 (its strike on the
  player, AI 0041f535), sHitRate 300, sAc 160 (the defence the player's strike
  divides by, 00443a34), sEvadeRate 1, and iExp 39,438,375, the largest of the
  reference rows. Its byAttackRange 0 and sBulk 10 (radius 0.1 m) give it a
  1.1 m strike distance (tools/assetc/ko_npc.py strike_distance, the band
  routine AI 0041d266: min(2r + 3, A + r + 1)), just past the 1 m the fight
  closes to, so it walks up to the player itself and strikes only beside it.
  From the default 5 m it struck the player, who walks one 0.075 m move a
  loop, six times before the player arrived (seven in all, 38 health down to
  11), and a slower loop under load let it kill the player (PQ-449);
* a "gate" K_NPC row of the other nation's group, shaped like the homeland camp
  gates: sDamage 0, iExp 0, sAc 0, sHitRate and sEvadeRate 194. It is byType 1
  and moves at 3 m/s; the real gates (type 150, speed 0) also take no damage
  from a user in KO (AI 00443a34, +0xc69 0), which is PQ-258's.

Against a native server on a disposable Postgres and Redis it checks over the
wire and in the database: every gate strike deals 0 and the player loses no
health to it, while the player's hits on the gate fall in the range its sAc 0
gives; every brute strike falls in the range its sDamage gives against the
player's defence, and the player's hits on it in the range its sAc 160 gives;
an operator kill of the gate commits a settlement whose N3T1 trailer carries
iExp 0 and awards nothing; an operator kill of the brute commits one awarding
9/5 of 39,438,375 (70,989,075, past the old 1,800,000 payload cap and the
13,200,000 durable check that migration 023 widens), and the realm keeps
running.
"""
import os
from pathlib import Path
import struct
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tests") not in sys.path:
    sys.path.append(str(ROOT / "tests"))
from isolation import once_per_run  # noqa: E402
from npc_reference_stats_live import NATION, check_readers, cook, ko_row, ko_spawn, live  # noqa: E402

OUT = ROOT / "build/pq252"
BIG_XP = 39438375  # the largest iExp of the OpenKO rows (PQ-251 evidence)
MONSTERS = [ko_row(110, strName="Sample Brute", sLevel=110, iHpPoint=30000, bySearchRange=6, byTracingRange=40,
                   byAttackRange=0, sBulk=10, sDamage=6, sHitRate=300, sAc=160, sEvadeRate=1, iExp=BIG_XP,
                   sPid=711)]
NPCS = [ko_row(500, strName="Sample Gate", sLevel=60, iHpPoint=50000, byActType=0, byGroup=3 - NATION,
               bySearchRange=6, byTracingRange=40, sDamage=0, sHitRate=194, sAc=0, sEvadeRate=194, iExp=0,
               sPid=30100)]
SPAWNS = [ko_spawn(110, 1, 0, 16), ko_spawn(500, 100, 0, -16)]
BRUTE, GATE = "demo:monster/110-sample-brute", "demo:npc/500-sample-gate"
C, V = 0.85000002384185791015625, 0.300000011920928955078125  # the f32 coefficients (content/damage.md)


@once_per_run
def prepare():
    """Cook the package; returns (package directory, templates by name)."""
    return cook(OUT, MONSTERS, NPCS, SPAWNS)


def player_range(attack, defense):
    """Player -> NPC (00443a34; server/src/damage.rs): trunc(c B + v R), R in 0..B."""
    base = attack * 200 // (defense + 240)
    return int(C * base), int(C * base + V * base)


def npc_range(attack, defense):
    """NPC -> player (0041f535): trunc(c B) + trunc(v R), x3/2 on the highest
    grade, capped at 2.6 x attack; 0 when B is 0."""
    base = attack * 200 // (defense + 240)
    return int(C * base), min((int(C * base) + int(V * base)) * 3 // 2, int(2.6 * attack))


def audit(p, sql, package, templates, Budget, first, owned):
    from world_peer import blob, integer

    def npcs():
        return {first(e, 2).decode(): e for e in p.entities.values() if first(e, 9) == 1}

    def me():
        return p.entities[p.id]

    def distance(e):
        return ((first(e, 3) - first(me(), 3)) ** 2 + (first(e, 5) - first(me(), 5)) ** 2) ** .5

    def strike(entity):
        """One melee attempt; returns (status, rolled damage) from ActionResult."""
        p.action_seq += 1
        p.send(15, integer(1, p.session) + integer(2, p.action_seq) + integer(3, entity) + blob(4, p.action_id))
        tag, data = p.until(16, 4)
        assert tag == 16, data
        return first(data, 2, b"").decode(), first(data, 4)

    def fight(name, hits, strikes):
        """Approaches `name` and attacks it until the player has landed `hits`
        and the NPC has struck the player `strikes` times. Returns (the
        player's hit damages, the NPC's (result, damage) strikes, the player's
        health before each NPC strike and after it). A dead player fails at
        once: its moves are refused and the NPC walks home, so the chase would
        otherwise only spend its step budget (PQ-449)."""
        t = templates[name]
        mine, theirs, health = [], [], []
        e = npcs()[name]
        entity, last = first(e, 1), first(e, 10)
        budget = Budget("fight " + name, strikes=80, steps=600, guard=120)
        while (len(mine) < hits or len(theirs) < strikes) and budget.ok(p.entities):
            before = first(me(), 7)
            p.pump(0.1)
            e = npcs()[name]
            if first(e, 10) != last and first(e, 25) == p.id:
                last = first(e, 10)
                theirs.append((first(e, 14, b"").decode(), first(e, 15)))
                health.append((before, first(me(), 7)))
            assert first(me(), 7) > 0, (budget.what, "the player died", mine, theirs, health)
            d = distance(e)
            if d > 1.0:
                budget.step()
                p.move((first(e, 3) - first(me(), 3)) / d, (first(e, 5) - first(me(), 5)) / d)
                continue
            p.move(0, 0)
            status, damage = strike(entity)
            budget.result(status)
            if status == "hit":
                mine.append(damage)
            elif status == "miss":
                assert damage == 0, damage
        assert first(npcs()[name], 7) > 0 and t["health"] > 0, (name, first(npcs()[name], 7))
        return mine, theirs, health

    def operator_kill(name):
        """The operator kill (PQ-194) credits the NPC's whole remaining health
        to this character; returns (gained XP, awarded_xp row, payload hex)."""
        e = npcs()[name]
        entity = first(e, 1)
        before = first(p.inventory, 4)
        p.send(28, integer(1, p.session) + blob(2, uuid.uuid4().hex) + blob(3, "kill") + integer(4, 0)
               + blob(5, (package / "release.sha256").read_text().strip()) + blob(7, "pq252 " + name)
               + integer(8, 0) + integer(10, entity))
        while True:
            tag, r = p.until(29, 4, seconds=10)
            assert tag == 29, r
            if first(r, 2) != b"pending":
                break
        assert first(r, 2) == b"killed", r
        deadline = time.monotonic() + 20
        while not sql(f"SELECT count(*) FROM encounter_settlements WHERE encounter={entity}") == "1":
            assert time.monotonic() < deadline, f"the {name} settlement never committed"
            p.pump(0.2)
        payload = sql(f"SELECT encode(payload,'hex') FROM encounter_settlements WHERE encounter={entity}")
        awarded = sql(f"SELECT awarded_xp FROM encounter_recipients WHERE encounter={entity}")
        # The settlement reaches the player's inventory (latest_settlement).
        award = Budget("award " + name, strikes=0, steps=0, guard=20)
        while award.ok(p.inventory) and first(p.inventory, 11) != entity:
            p.pump(0.2)
        return first(p.inventory, 4) - before, int(awarded), payload

    p.pump(0.3)
    assert set(npcs()) == {BRUTE, GATE}, npcs().keys()
    attack, defense = first(p.stats, 1), first(p.stats, 2)
    assert attack > 0, p.stats
    brute, gate = templates[BRUTE], templates[GATE]
    assert (brute["xp"], brute["attack"], brute["damage"], brute["defense"], brute["accuracy"],
            brute["evasion"], brute["attack_range"]) == (BIG_XP, 6, 6, 160, 300, 1, 1.1), brute
    assert (gate["xp"], gate["attack"], gate["damage"], gate["defense"], gate["accuracy"],
            gate["evasion"]) == (0, 0, 0, 0, 194, 194), gate
    print(f"PASS KO-cooked combat columns: brute (sDamage 6, sAc 160, sHitRate 300, sEvadeRate 1, iExp {BIG_XP}, "
          "strike distance 1.1 m), "
          f"gate (sDamage 0, sAc 0, iExp 0); player attack {attack}, defence {defense}", flush=True)
    # 1. The gate's strikes deal nothing; the player's hits fall in the range sAc 0 gives.
    mine, theirs, health = fight(GATE, 3, 2)
    lo, hi = player_range(attack, gate["defense"])
    assert all(lo <= d <= hi for d in mine), (mine, lo, hi)
    assert all(d == 0 and r in ("hit", "miss") for r, d in theirs), theirs
    assert all(after >= before for before, after in health), health
    print(f"PASS sDamage 0 gate: {len(theirs)} strikes {theirs} deal 0 and the player keeps its health; the player's "
          f"hits {mine} fall in {lo}..{hi} (sAc 0)", flush=True)
    # 2. The gate's kill: iExp 0 awards nothing, and the settlement records it.
    gained, awarded, payload = operator_kill(GATE)
    assert payload.endswith((b"N3T1" + struct.pack("<II", 60, 0)).hex()), payload[-40:]
    assert (gained, awarded) == (0, 0), (gained, awarded)
    print("PASS iExp 0 gate kill: settlement committed with the N3T1 level 60, XP 0 reward, 0 XP awarded", flush=True)
    # 3. The brute's strikes fall in the range its sDamage gives against the
    # player's defence; the player's hits in the range its sAc 160 gives.
    mine, theirs, health = fight(BRUTE, 3, 2)
    lo, hi = player_range(attack, brute["defense"])
    assert all(lo <= d <= hi for d in mine), (mine, lo, hi)
    nlo, nhi = npc_range(brute["attack"], defense)
    assert nhi > 0, (nlo, nhi)
    assert all((r == "miss" and d == 0) or (r == "hit" and nlo <= d <= nhi) for r, d in theirs), (theirs, nlo, nhi)
    print(f"PASS sDamage 6 brute: strikes {theirs} fall in {nlo}..{nhi} against defence {defense}; the player's hits "
          f"{mine} fall in {lo}..{hi} (sAc 160); the player's health stays at or above "
          f"{min(after for _, after in health)}", flush=True)
    # 4. The brute's kill: 9/5 of iExp 39,438,375 (level 110 against level 1),
    # past the old payload and durable caps; the realm keeps running.
    level = first(p.inventory, 5) or 1
    assert brute["level"] - level >= 8, level
    gained, awarded, payload = operator_kill(BRUTE)
    assert payload.endswith((b"N3T1" + struct.pack("<II", 110, BIG_XP)).hex()), payload[-40:]
    assert gained == awarded == BIG_XP * 9 // 5 == 70989075, (gained, awarded)
    tick = p.tick
    p.pump(1.0)
    assert p.tick > tick and owned(), (tick, p.tick)
    print(f"PASS iExp {BIG_XP} brute kill: {gained} XP awarded (x9/5), recorded in encounter_recipients and the "
          "N3T1 trailer, and the realm keeps running", flush=True)


if __name__ == "__main__":
    os.chdir(ROOT)
    package, templates = prepare()
    check_readers(package)
    print("PASS N3N3 engine 37 package from KO combat rows: both readers accept iExp 39,438,375 and 0, sDamage 0",
          flush=True)
    live(package, templates, audit, OUT, "pq252")
