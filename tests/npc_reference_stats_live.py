"""PQ-251: KO reference stats cooked into N3N3 templates (tools/assetc/ko_npc.py), live.

The package is the PQ-249 engine 37 fixture (tests/npc_templates_live.py) on a
256 m flat heightfield whose NPC templates come from synthetic K_MONSTER, K_NPC
and K_NPCPOS rows (original values, not reference rows) through the operator
import (tools/assetc/ko_tables.py) and the KO template cook, with the package's
players seated in nation 1:

* a "boss" K_MONSTER row at homeland scale: level 110, 150,000 HP, run speed
  9 m/s, search 25 m, tracing 60 m, attack range 5 with radius 1 m (strike
  distance 5 m), 1,510 ms attacks (31 ticks), act type 5 (aggressive);
* a "runt" K_MONSTER row: level 110, 4 HP, act type 1 (passive);
* a "guard" K_NPC row (spawn ActType 101) of group 1, act type 7: passive,
  because its group is the package's nation.

Against a native server on a disposable Postgres and Redis it checks over the
wire: each NPC carries its template's name, looks key, health and maximum
health; the boss acquires the player from 20 m (past the old 10 m bound),
chases at its 9 m/s (0.45 m a tick, past the old 3 m/s), stops and strikes
from its strike distance at its 31-tick cadence; the guard never takes the
player beside it; the level 110 runt's kill awards the top level-difference
multiplier and the durable settlement records level 110 in its N3T1 trailer;
an operator kill of the 150,000 HP boss records 150,000 credit (past the old
100,000 bound), commits its settlement and leaves the realm running.
"""
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tests") not in sys.path:
    sys.path.append(str(ROOT / "tests"))
from isolation import once_per_run  # noqa: E402

OUT = ROOT / "build/pq251"
NATION = 1
ORIGIN = 128  # synthetic KO (x, z) -> n3e (x - 128, z - 128)


def ko_row(sid, **kw):
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    import ko_tables
    row = {c: 1 for c, _, _ in ko_tables.COLUMNS["K_MONSTER"]}
    # Combat columns (PQ-252): iExp 10; sDamage 2, so a strike deals at most 1
    # against the player's 38 health; sAc 0, sHitRate 100, sEvadeRate 1.
    row.update(sSid=sid, strName="Sample %d" % sid, sPid=sid + 1, sLevel=30, iHpPoint=500, sAttackDelay=1500,
               bySpeed1=1, bySpeed2=3, sStandtime=1000, byAttackRange=5, bySearchRange=6, byTracingRange=30,
               byActType=5, byGroup=0, sSize=100, sBulk=100, byDirectAttack=0,
               iExp=10, sDamage=2, sAc=0, sHitRate=100, sEvadeRate=1)
    row.update(kw)
    return row


def ko_spawn(npc_id, act, x, z):
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    import ko_tables
    row = {c: 0 for c, _, _ in ko_tables.COLUMNS["K_NPCPOS"]}
    del row["path"]
    row.update(ZoneID=7, NpcID=npc_id, ActType=act, LeftX=x + ORIGIN, RightX=x + ORIGIN, TopZ=z + ORIGIN,
               BottomZ=z + ORIGIN, NumNPC=1, RegTime=30)
    return row


MONSTERS = [ko_row(10, strName="Sample Boss", sLevel=110, iHpPoint=150000, bySpeed2=9, bySearchRange=25,
                   byTracingRange=60, sAttackDelay=1510, sPid=701),
            ko_row(20, strName="Sample Runt", sLevel=110, iHpPoint=4, byActType=1, sPid=702)]
NPCS = [ko_row(400, strName="Sample Guard", byActType=7, byGroup=NATION, iHpPoint=10000, sLevel=60, sPid=21000)]
SPAWNS = [ko_spawn(10, 1, 0, 20), ko_spawn(20, 1, -3, 0), ko_spawn(400, 101, 3, 0)]
BOSS, RUNT, GUARD = "demo:monster/10-sample-boss", "demo:monster/20-sample-runt", "demo:npc/400-sample-guard"


@once_per_run
def prepare():
    """Cook the package; returns (package directory, templates by name)."""
    return cook(OUT, MONSTERS, NPCS, SPAWNS)


def cook(build, monsters, npcs, spawns):
    """The PQ-249 engine 37 fixture on a flat 256 m heightfield whose templates
    the KO cook builds from these rows, written as an operator export under
    `build`; returns (package directory, templates by name)."""
    from npc_templates_live import prepare as base
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    import main
    import ko_npc
    import ko_tables

    export = build / "export"
    shutil.rmtree(export, ignore_errors=True)
    export.mkdir(parents=True)
    for table, rows in (("K_MONSTER", monsters), ("K_NPC", npcs), ("K_NPCPOS", spawns)):
        (export / (table + ".json")).write_text(json.dumps(rows))
    tables = {t: ko_tables.load(t, export) for t in ko_tables.TABLES}
    # This engine 37 package has no looks table, so it carries no drawn scale
    # (an N3N4 scale needs one, PQ-272); sSize is still bounds-checked.
    templates, spawns = ko_npc.zone_templates(tables, 7, "demo", NATION, drawn_scale=False)
    source = base().parent / "source"
    root, out = build / "source", build / "package"
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(source, root)
    scene = json.loads((root / "scene.json").read_text())
    scene["heightfield"] = dict(width=129, depth=129, origin=[-128, 0, -128], spacing=2, heights=[0] * 129 * 129)
    (root / "scene.json").write_text(json.dumps(scene))
    m = json.loads((root / "package.json").read_text())
    points, slots = [], []
    for row, name in spawns:
        for _ in range(row["NumNPC"]):
            points.append([float(row["LeftX"] - ORIGIN), float(row["TopZ"] - ORIGIN)])
            # AI 0043893e: RegTime seconds, 30 below 15 (D-106).
            slots.append(dict(area=[0, 0, 0, 0], respawn_ticks=max(row["RegTime"], 30) * 20, template=name))
    m["gameplay"].update(spawns=points, spawn_x=0, spawn_z=0)
    m["npc"]["templates"] = templates
    m["npc"]["slots"] = slots
    (root / "package.json").write_text(json.dumps(m))
    main.cook(root, out)
    return out.resolve(), {t["name"]: t for t in templates}


def check_readers(package):
    for cmd in [["build/client/n3e-asset-check", str(package)], ["target/debug/n3e-server", "--check-content"]]:
        p = subprocess.run(cmd, cwd=ROOT, env={**os.environ, "N3E_PACKAGE": str(package)}, capture_output=True, text=True)
        assert p.returncode == 0, (cmd, p.stdout[-600:], p.stderr[-600:])


POSTGRES = "postgres:17.4-bookworm@sha256:304ab813518754228f9f792f79d6da36359b82d8ecf418096c636725f8c930ad"
REDIS = "redis:7.4.2-bookworm@sha256:fbdbaea47b9ae4ecc2082ecdb4e1cea81e32176ffb1dcf643d422ad07427e5d9"


def live(package, templates, check=None, build=OUT, label="pq251"):
    """Runs `check` (this suite's `audit` by default) against a native server on
    a disposable Postgres and Redis serving `package`; logs go under `build`."""
    from isolation import DISPOSABLE_POSTGRES, container_logs, free_ports
    from readiness import wait_postgres
    from world_peer import Budget, Peer as BasePeer, fields, first
    import urllib.request

    class Peer(BasePeer):
        """Records every frame from the first: its tick, the player's (x, z) and
        each NPC's (x, z, behavior, strike target) by name; and the player's
        derived stats."""
        frames = []
        stats = {}

        def _parse(self, envelope):
            tag, data = super()._parse(envelope)
            if tag == 10 and data.get(13):
                self.stats = fields(data[13][0])
            if tag == 10 and self.id in self.entities:
                me = self.entities[self.id]
                self.frames.append((self.tick, (first(me, 3), first(me, 5)), {
                    first(e, 2).decode(): (first(e, 3), first(e, 5), first(e, 12, b"").decode(), first(e, 25))
                    for e in self.entities.values() if first(e, 9) == 1}))
            return tag, data

    manifest = json.loads((package / "recipe.json").read_text())["manifest"]
    out = build / "live"
    out.mkdir(parents=True, exist_ok=True)
    server_binary = str(Path(os.environ.get("N3E_TEST_SERVER", "target/debug/n3e-server")).resolve())
    name = f"n3e-{label}-" + uuid.uuid4().hex[:10]
    password = "test-only-" + uuid.uuid4().hex
    containers, server, log = [], None, None

    def run(*cmd, env=None, stdin=None):
        p = subprocess.run(cmd, env=env, input=stdin, capture_output=True, text=True, timeout=120)
        assert p.returncode == 0, (cmd, p.returncode, p.stdout, p.stderr)
        return p.stdout

    def sql(query):
        return run("docker", "exec", name, "psql", "-v", "ON_ERROR_STOP=1", "-tAq", "-U", "n3e", "-d", "n3e",
                   "-c", query).strip()

    try:
        for suffix, image, port, extra in [
            ("", POSTGRES, 5432, ["-e", "POSTGRES_USER=n3e", "-e", "POSTGRES_PASSWORD=test-only",
                                  "-e", "POSTGRES_DB=n3e", *DISPOSABLE_POSTGRES]),
            ("-redis", REDIS, 6379, []),
        ]:
            run("docker", "run", "--rm", "-d", "--name", name + suffix, *extra, "-p", f"127.0.0.1::{port}", image)
            containers.append(name + suffix)
        pg = wait_postgres(name)
        redis = run("docker", "port", name + "-redis", "6379").split()[0]
        listen, health = free_ports(2)
        realm = "test-" + name
        env = dict(os.environ, DATABASE_URL=f"host=127.0.0.1 port={pg} user=n3e password=test-only dbname=n3e",
                   REDIS_ADDRESS=redis, N3E_PACKAGE=str(package), N3E_REALM=realm,
                   N3E_LISTEN=f"127.0.0.1:{listen}", N3E_HEALTH=f"127.0.0.1:{health}")
        run(server_binary, "migrate", env=env)
        run(server_binary, "convert-progression", env={**env, "N3E_TEST_PROGRESSION": "disposable"})
        run(server_binary, "account-create", "explorer", env=env, stdin=password + "\n")
        log = open(out / "server.log", "w")
        server = subprocess.Popen([server_binary], env=env, stdout=log, stderr=log)
        deadline = time.monotonic() + 30
        while True:
            assert server.poll() is None, (out / "server.log").read_text()[-2000:]
            assert time.monotonic() < deadline, "server never reported ready"
            try:
                if urllib.request.urlopen(f"http://127.0.0.1:{health}/ready", timeout=0.2).status == 200:
                    break
            except OSError:
                time.sleep(0.1)
        p = Peer(listen, "explorer", password, content=(package / "release.sha256").read_text().strip(),
                 game=manifest["game_id"], protocol=manifest["protocol_version"])
        p.create("Explorer")
        assert p.select(p.characters[0][0])[0] == 10
        # The operator kill of step 6 needs entity.kill on this character (PQ-194).
        run(server_binary, "role", "grant", "explorer", str(p.characters[0][0]), realm, "entity.kill", env=env)

        def owned():
            """The server still runs and reports ready (it owns the realm)."""
            try:
                return server.poll() is None and urllib.request.urlopen(
                    f"http://127.0.0.1:{health}/ready", timeout=1).status == 200
            except OSError:
                return False
        (check or audit)(p, sql, package, templates, Budget, first, owned)
        p.logout()
    finally:
        if server is not None:
            server.kill()
            server.wait()
        if log is not None:
            log.close()
        for c in containers:
            container_logs({name: "postgres", name + "-redis": "redis"}[c], ["docker", "logs", "--timestamps", c])
        for c in containers:
            subprocess.run(["docker", "rm", "-f", c], capture_output=True)


def audit(p, sql, package, templates, Budget, first, owned):
    def npcs():
        return {first(e, 2).decode(): e for e in p.entities.values() if first(e, 9) == 1}

    def me():
        return p.entities[p.id]

    def distance(e):
        return ((first(e, 3) - first(me(), 3)) ** 2 + (first(e, 5) - first(me(), 5)) ** 2) ** .5

    # 1. Each NPC carries its cooked template's name, looks key, health and maximum.
    p.pump(0.3)
    seen = npcs()
    assert set(seen) == {BOSS, RUNT, GUARD}, seen.keys()
    for n, e in seen.items():
        t = templates[n]
        got = (first(e, 31, b"").decode(), first(e, 7), first(e, 32))
        assert got == (t["looks"], t["health"], t["health"]), (n, got)
    boss = templates[BOSS]
    assert (boss["health"], boss["level"], boss["speed"], boss["search_range"], boss["attack_range"],
            boss["attack_ticks"]) == (150000, 110, 9, 25, 5.0, 31), boss
    print("PASS KO-cooked templates on the wire: own name, looks key and health (boss 150,000, guard 10,000, "
          "runt 4) and max_health", flush=True)
    # 2. The boss acquires the standing player from 20 m and chases at 9 m/s;
    # 3. it stops inside its strike distance (5 m), short of the player, and
    # strikes there at its own cadence (31 ticks).
    strikes = []
    wait = Budget("boss strikes", strikes=0, steps=0, guard=40)
    while len(strikes) < 2 and wait.ok(p.entities):
        p.pump(0.1)
        e = npcs()[BOSS]
        if first(e, 25) == p.id and first(e, 10) and (not strikes or first(e, 10) != strikes[-1][0]):
            strikes.append((first(e, 10), distance(e)))
    assert len(strikes) >= 2, (strikes, p.frames[-3:])

    def gap(frame, n):
        (px, pz), (x, z) = frame[1], frame[2][n][:2]
        return ((x - px) ** 2 + (z - pz) ** 2) ** .5

    start = gap(p.frames[0], BOSS)
    # The first frame in which it chases (field 25 is only the strike target).
    acquired = next(f for f in p.frames if f[2][BOSS][2] == "chase")
    assert 19 <= start <= 21 and gap(acquired, BOSS) > 19, (start, acquired)
    path = [(f[0], *f[2][BOSS][:3]) for f in p.frames]
    rates = [((x1 - x0) ** 2 + (z1 - z0) ** 2) ** .5 / (t1 - t0)
             for (t0, x0, z0, b0), (t1, x1, z1, b1) in zip(path, path[1:]) if t1 > t0 and b0 == b1 == "chase"]
    assert rates and 0.40 <= max(rates) <= 0.451, rates
    # The last chase substep (0.15 m) that enters the 5 m range ends the chase.
    assert all(4.8 <= d <= 5.0 + 1e-3 for _, d in strikes), strikes
    assert strikes[1][0] - strikes[0][0] >= boss["attack_ticks"], strikes
    print(f"PASS boss acquires from {gap(acquired, BOSS):.1f} m (search 25 m), chases at {max(rates) * 20:.2f} m/s "
          f"(run speed 9) and strikes from {strikes[0][1]:.2f} m (strike distance 5 m) every "
          f"{strikes[1][0] - strikes[0][0]} ticks (31)", flush=True)
    # 4. The guard, of the package's nation, never takes the player 3 m away.
    guard = [(f[0], gap(f, GUARD), *f[2][GUARD][2:]) for f in p.frames]
    assert all(d <= 3.5 and b == "idle" and target != p.id for _, d, b, target in guard), guard[-5:]
    assert guard[-1][0] - guard[0][0] >= 60, (guard[0], guard[-1])
    print(f"PASS same-nation guard (act type 7, group 1) stays idle 3 m from the player for "
          f"{guard[-1][0] - guard[0][0]} ticks", flush=True)
    # 5. The level 110 runt's kill: the top level-difference multiplier, and the
    # settlement records level 110.
    runt = templates[RUNT]
    level = first(p.inventory, 5) or 1
    e = npcs()[RUNT]
    entity = first(e, 1)
    before = first(p.inventory, 4)
    kill = Budget("kill runt", strikes=60, guard=120)
    while kill.ok(p.inventory, p.entities) and first(p.inventory, 4) == before:
        p.pump(0.1)
        alive = [v for v in p.entities.values() if first(v, 1) == entity and first(v, 7) > 0]
        if alive and distance(alive[0]) <= 1.0:
            kill.result(p.action(entity))
        elif alive:
            kill.step()
            d = distance(alive[0])
            p.move((first(alive[0], 3) - first(me(), 3)) / d, (first(alive[0], 5) - first(me(), 5)) / d)
    gained = first(p.inventory, 4) - before
    assert runt["level"] - level >= 8 and gained == runt["xp"] * 9 // 5, (gained, runt, level)
    payload = sql(f"SELECT encode(payload,'hex') FROM encounter_settlements WHERE encounter={entity}")
    trailer = (b"N3T1" + struct.pack("<II", 110, runt["xp"])).hex()
    assert payload.endswith(trailer), (payload[-40:], trailer)
    import hashlib
    definition = sql("SELECT encode(definition,'hex') FROM active_reward_policy")
    assert definition == hashlib.sha256((package / "progression.bin").read_bytes()).hexdigest(), definition
    print(f"PASS level 110 runt kill: {gained} XP (x9/5 of {runt['xp']}), settlement records the N3T1 "
          "level 110 reward", flush=True)
    # 6. A kill above the old 100,000 credit bound: the operator kill (PQ-194)
    # credits the boss's whole 150,000 health; the settlement commits and the
    # realm keeps running (a refused settlement would stop the simulation).
    from world_peer import blob, integer
    e = npcs()[BOSS]
    entity, health = first(e, 1), first(e, 7)
    assert health > 100000, health
    before = first(p.inventory, 4)
    request = uuid.uuid4().hex
    p.send(28, integer(1, p.session) + blob(2, request) + blob(3, "kill") + integer(4, 0)
           + blob(5, (package / "release.sha256").read_text().strip()) + blob(7, "pq251 boss") + integer(8, 0)
           + integer(10, entity))
    while True:
        tag, r = p.until(29, 4, seconds=10)
        assert tag == 29, r
        if first(r, 2) != b"pending":
            break
    assert first(r, 2) == b"killed", r
    deadline = time.monotonic() + 20
    while not sql(f"SELECT count(*) FROM encounter_settlements WHERE encounter={entity}") == "1":
        assert time.monotonic() < deadline, "the boss's settlement never committed"
        p.pump(0.2)
    payload = sql(f"SELECT encode(payload,'hex') FROM encounter_settlements WHERE encounter={entity}")
    assert payload.endswith((b"N3T1" + struct.pack("<II", 110, boss["xp"])).hex()), payload[-40:]
    credit = sql(f"SELECT credit FROM encounter_recipients WHERE encounter={entity}")
    assert credit == str(health), (credit, health)
    award = Budget("boss award", strikes=0, steps=0, guard=20)
    while first(p.inventory, 4) == before and award.ok(p.inventory):
        p.pump(0.2)
    gained = first(p.inventory, 4) - before
    assert gained == boss["xp"] * 9 // 5, gained
    tick = p.tick
    p.pump(1.0)
    assert p.tick > tick and owned(), (tick, p.tick)
    print(f"PASS operator kill of the 150,000 HP boss: credit {credit} recorded, settlement committed with the "
          f"N3T1 level 110 reward, {gained} XP, and the realm keeps running", flush=True)


if __name__ == "__main__":
    os.chdir(ROOT)
    package, templates = prepare()
    check_readers(package)
    print("PASS N3N3 engine 37 package from KO rows: both readers accept level 110, 150,000 HP, 9 m/s and 25 m search",
          flush=True)
    live(package, templates)
