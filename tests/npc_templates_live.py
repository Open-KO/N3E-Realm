"""PQ-249: many NPC templates in one package (N3N3, engine 37 / wire 30), live.

The package is the original synthetic item-drops fixture (tests/item_drops_live.py)
carried to engine 37 the way tests/appearance.py carries it to engine 33, plus a
synthetic skill (engine 34/35) and an N3N3 NPC policy with two templates: a
passive "drudge" and an aggressive "brute", one per spawn slot, both in one view.

Against a native server on a disposable Postgres and Redis it checks, over the
wire: each NPC carries its own template name, looks key, health and maximum
health; the passive template never acquires a player beside it while the
aggressive one does; each template's strikes deal damage inside the range its own
attack value gives against the player's defence; killing each one awards its own
template level and XP (solo award), and the durable settlement records that
reward (its payload ends with the N3T1 trailer) while the realm's reward
definition stays the package's. A killed NPC respawns with its own template.

PQ-466 (D-234): the skill policy is N3K3 with a too-far notice and two strikes
on an NPC. With N3E_GRAPHICAL=1 a fresh caster stands about 7 m from the NPCs
and the real client selects the nearest one and uses the bolt (start limit
3 m), then the spark (27 m): the bolt posts the notice and takes no action
sequence number, the spark goes out as action 1 and another player sees it
cast.

PQ-469 (D-235): the policy is N3K4 with a failed line. A third press sends the
bolt without the client's hint; the server refuses it out_of_range and the
client draws the policy's failed line, formatted with "Bolt", in its colour.

PQ-479 (D-243): the policy is N3K5 with refusal lines. A fourth press sends the
surge, whose cost no character can pay; the server refuses it
insufficient_resource at its acceptance and the client draws the policy's line
for that status, formatted with "Surge", in its colour.

PQ-481 (D-245): the client picks a skill's recipient as 1298's skill start
does. A press of the spark before any target is selected is held back with no
action and no line. A press of the nova, whose level no character has, is sent
(the client has no level test); the server refuses it level_required and the
client draws the policy's line for that status. A press of the heal with the
NPC selected goes to the caster itself.
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

OUT = ROOT / "build/pq249"
# Two templates in one view (spawn slots 0 and 1). Their strike ranges do not
# overlap (attack 4 and 12 against the player's defence of 1: 2-3 and 7-13). The
# unarmed player deals 2-3 a strike (92 % to hit) and has 38 health, so health
# stays low (2 and 3 strikes) and the brute slow (100 ticks). The player's
# survival is not left to the rolls (PQ-399): it kills the drudge first, from full
# health, then rests back to full before the brute's two observed strikes and its
# kill, so each fight starts at 38 and the worst one (three brute strikes, at most
# 39) is a rare roll on top of a rare roll. A player killed mid-fight ends the
# kill loop at once with its own message: the healed NPC then takes a fresh
# encounter identity (gameplay.rs), which the loop would otherwise wait on.
TEMPLATES = [
    dict(name="demo:creature/drudge", looks="demo:looks/drudge", acquisition="passive", health=4, level=1,
         xp=10, damage=1, attack=4, defense=0, accuracy=100, evasion=1, attack_ticks=20, speed=3,
         attack_range=1, search_range=3, tracing_range=8),
    dict(name="demo:creature/brute", looks="demo:looks/brute", acquisition="aggressive", health=6, level=4,
         xp=50, damage=1, attack=12, defense=0, accuracy=100, evasion=1, attack_ticks=100, speed=3,
         attack_range=1, search_range=6, tracing_range=12),
]
SPAWNS = [[-5, -5], [5, -5]]
# PQ-466 (D-234): the client's too-far line (one %s, the skill's label), and
# where the player stands for the graphical skill presses: about 7 m from
# either spawn (beyond the brute's 6 m search range; the fixture's ground
# ends about half a metre further south), beyond the bolt's 3 m start limit
# and within the spark's 27 m.
NOTICE = "%s failed: the target is too far"
SKILL_SPOT = (0.0, -10.0)
# PQ-469 (D-235): the client's line for the server's out_of_range refusal of a
# skill it sent, and its colour (1298's 00586fa0 posts text 0xfa4 in 0xffff3b3b).
FAILED = dict(text="%s refused by the server", color=0xffff3b3b)
# PQ-479 (D-243): the client's lines for the server's refusals of a skill at
# its acceptance (1298 posts its own text, e.g. 3004 for too little MP, in
# 0xffffff00, 0057f7f0).
REFUSALS = [dict(status="insufficient_resource", target="any", text="%s: not enough resource", color=0xffffff00),
            dict(status="target_dead", target="npc", text="Casting failed", color=0xffff3b3b),
            # PQ-481 (D-245): 1298 has no level test before it sends; Ebenezer
            # answers -100 and 1298 posts text 0xfa2 in 0xffff3b3b (00586fa0).
            dict(status="level_required", target="any", text="%s: casting failed", color=0xffff3b3b)]


@once_per_run
def prepare():
    """Cook the engine-37 package; returns its directory."""
    from item_drops_live import prepare as base
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    import importlib.util
    import main
    from common import string, u
    # By path: tests/render_detail.py (a check) shares the cooker module's name.
    spec = importlib.util.spec_from_file_location("render_detail", ROOT / "tools/assetc/render_detail.py")
    render_detail = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(render_detail)

    # The variant the *_db suites cook (ttl=10): once_per_run refuses two
    # variants that write the same directory in one live run.
    source = base(full=True, ttl=10).parent / "source"
    root, out = OUT / "source", OUT / "package"
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(source, root)
    m = json.loads((root / "package.json").read_text())
    gear = m["equipment"]["items"][0]
    # Engine 29: world, render detail, exploration and appearance (tests/appearance.py).
    m.update(world="map.bin", render_detail="detail.bin",
             exploration=dict(turbo_multiplier=10, fog_start=192, fog_end=256, fog_color=[.6, .7, .8], lod="lod.bin"),
             appearance=[dict(item=gear["id"], slot=gear["slots"][0])])
    vs = [[0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0], [4, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0], [0, 0, 4, 0, 1, 0, 0, 1, 0, 0, 0, 0]]
    (root / "map.bin").write_bytes(b"N3W1" + u(16) + u(16) + u(8) + u(1) + bytes([255]) * 1024 + u(3)
                                   + b"".join(struct.pack("<12f", *v) for v in vs) + u(3) + u(0) + u(1) + u(2))
    (root / "lod.bin").write_bytes(b"N3L2" + u(1) + struct.pack("<5f", 2, 0, 2, 4, 1) + u(0) + u(1)
                                   + struct.pack("<f", 0) + u(3) + u(0) + u(1) + u(2))

    def geometry(slot):
        return ([([x, 0, z], [0, 1, 0], [x, z], [0] * 4, [1, 0, 0, 0], slot) for x, z in [(0, 0), (1, 0), (0, 1)]], [0, 1, 2])
    (root / "detail.bin").write_bytes(render_detail.serialize(
        view=[1.134464, .5, 256], thresholds=[[6, 18, 32, 128]] * 4, workload=[30, 60, 100], world_count=1,
        textures=[[(16, 16, bytes([255]) * 1024)]] * 3, radius=1, levels=[geometry(1)] * 4,
        appearances=[([1], [geometry(2)] * 4)]))
    # Engine 30: rest and the sit/idle/stand clips.
    m["rest"] = dict(interval_ticks=101, sit_cooldown_ticks=60, levels=[[4, 5, 30, 3]])
    idle = m["animation"][0]
    m["animation"] = m["animation"][:7] + [{**idle, "loop_blend": False}, idle, {**idle, "loop_blend": False}] + m["animation"][7:]
    for state in ["sit-down", "sit-idle", "stand-up"]:
        m["presentation"][f"player-{state}.bin"] = m["presentation"]["player-idle.bin"]
    # Engines 31 and 32: combat animation profiles with timed, moving clips.
    m["combat_animation"] = dict(
        clips=[dict(source=m["presentation"]["player-idle.bin"], **{**idle, "loop_blend": False}) for _ in range(3)],
        profiles=[dict(ready=0, attacks=[1, 2], interval_ms=1140, moving=2),
                  dict(ready=0, attacks=[1, 2], interval_ms=1140, moving=2)],
        slots=[gear["slots"][0]], rows=[dict(items=[None], profile=1), dict(items=[gear["id"]], profile=2)],
        upper_nodes=[1])
    # Engine 33: one consumable.
    potion = next(i for i in m["inventory"]["items"] if i["durability"] == 0 and i["stack_limit"] > 1)
    m["consumables"] = [dict(item=potion["id"], health=90, resource=0, delay_ms=500, cooldown_ms=2000)]
    # Engines 34 and 35: one synthetic skill and its clip (tests/skills.py).
    skill = dict(id="demo:skill/heal", label="Heal", **{"class": "demo:class/test"}, level=1, cost=5, cast_ms=1500,
                 cooldown_ms=2000, range=25, target=1, amount=15, survival=80, attribute=4, resistance=0, weapons=[],
                 animation=0, cast_effect="cast", cast_joints=[0], target_effect="heal", target_joint=-1)
    # PQ-465 (D-232): N3K2's reach; no margins, the range in 3-D. PQ-466
    # (D-234): N3K3's notice, and two strikes on an NPC whose start limits
    # (range + the melee radii 2) lie either side of the player's distance
    # from the NPCs in the graphical run (SKILL_SPOT).
    strike = dict(skill, target=2, amount=1, cooldown_ms=0, target_effect="cast")
    m["skills"] = dict(archetype="demo:class/test", label="Test", reach=dict(start=0, hold=0, plane="3d"),
                       notice=NOTICE, failed=FAILED, refusals=REFUSALS,
                       skills=[skill, dict(strike, id="demo:skill/bolt", label="Bolt", range=1),
                               dict(strike, id="demo:skill/spark", label="Spark", range=25),
                               dict(strike, id="demo:skill/surge", label="Surge", range=25, cost=100000),
                               # PQ-481 (D-245): a level no character in this run has.
                               dict(strike, id="demo:skill/nova", label="Nova", range=25, level=50)])
    shutil.copyfile(root / m["presentation"]["player-idle.bin"], root / "player-skill-0.bin")
    # The client draws a skill's cast and target effects: one blank frame each.
    clip = lambda name: string(name) + u(0) + u(10) + u(1) + u(0)
    (root / "effects.bin").write_bytes(b"N3EF" + u(1) + u(1) + u(1) + bytes(4) + u(2) + clip("cast") + clip("heal") + u(0))
    m["presentation"]["effects.bin"] = "effects.bin"
    # Engine 37: N3N3 with two templates, one per slot, both slots in one view.
    m["gameplay"]["spawns"] = SPAWNS
    m["npc"] = dict(model="reference_templates_v3", scan_ticks=5, acquire_ticks=5, stuck_ticks=40, chase_ticks=400,
                    return_ticks=200, recovery_ticks=20, renew_on_hit=True, return_heal=True,
                    retaliate_returning=True, return_speed_percent=100, regen_interval_ticks=0, regen_divisor=1,
                    spawn_tries=1, templates=TEMPLATES,
                    slots=[dict(area=[0, 0, 0, 0], respawn_ticks=60, template=t["name"]) for t in TEMPLATES])
    m.update(engine_version=37, protocol_version=30)
    (root / "package.json").write_text(json.dumps(m))
    main.cook(root, out)
    return out.resolve()


def check_readers(package):
    """Both readers accept the package and bind the same release identity."""
    results = []
    for cmd in [["build/client/n3e-asset-check", str(package)], ["target/debug/n3e-server", "--check-content"]]:
        p = subprocess.run(cmd, cwd=ROOT, env={**os.environ, "N3E_PACKAGE": str(package)}, capture_output=True, text=True)
        assert p.returncode == 0, (cmd, p.stdout[-600:], p.stderr[-600:])
        results.append(p.stdout.splitlines())
    assert set(results[0]) & set(results[1]), "readers disagree on the release"


POSTGRES = "postgres:17.4-bookworm@sha256:304ab813518754228f9f792f79d6da36359b82d8ecf418096c636725f8c930ad"
REDIS = "redis:7.4.2-bookworm@sha256:fbdbaea47b9ae4ecc2082ecdb4e1cea81e32176ffb1dcf643d422ad07427e5d9"


def strike_range(attack, defense):
    """Inclusive damage bounds of one hit (server/src/damage.rs, NPC side): the
    0.85 and 0.30 parts of the base, x1.5 on the highest grade, capped at 2.6 x
    attack. A miss is 0 and reported as such."""
    base = attack * 200 // (defense + 240)
    lo = int(0.85 * base)
    hi = min((int(0.85 * base) + int(0.30 * base)) * 3 // 2, int(2.6 * attack))
    return lo, hi


def live(package):
    from isolation import DISPOSABLE_POSTGRES, container_logs, free_ports
    from readiness import wait_postgres
    from world_peer import Budget, Peer as BasePeer, fields, first
    import urllib.request

    class Peer(BasePeer):
        stats = {}

        def _parse(self, envelope):
            tag, data = super()._parse(envelope)
            if tag == 10 and data.get(13):
                self.stats = fields(data[13][0])
            return tag, data

    manifest = json.loads((package / "recipe.json").read_text())["manifest"]
    out = OUT / "live"
    out.mkdir(parents=True, exist_ok=True)
    server_binary = str(Path(os.environ.get("N3E_TEST_SERVER", "target/debug/n3e-server")).resolve())
    name = "n3e-pq249-" + uuid.uuid4().hex[:10]
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
        p.pump(0.5)
        audit(p, sql, package, Budget, first)
        p.logout()
        if os.environ.get("N3E_GRAPHICAL") == "1":
            # The real test client takes the engine 37 package and the wire 30
            # entities (its environment renders it offscreen, PQ-121). PQ-466
            # (D-234): it selects the nearest NPC (Z) and uses the bolt, then
            # the spark, while another player watches the caster's casts.
            # A fresh caster (the explorer may still hold the brute's attention
            # and has spent its health) walks from the start to SKILL_SPOT once
            # both NPCs stand at their spawns, one movement per acknowledged
            # movement (field 6), as tests/moradon_route.py's walker steers.
            peers = {}
            for account in ("caster", "observer"):
                run(server_binary, "account-create", account, env=env, stdin=password + "\n")
                peers[account] = Peer(listen, account, password,
                                      content=(package / "release.sha256").read_text().strip(),
                                      game=manifest["game_id"], protocol=manifest["protocol_version"])
                peers[account].create(account.title())
                assert peers[account].select(peers[account].characters[0][0])[0] == 10
            c, o = peers["caster"], peers["observer"]
            deadline = time.monotonic() + 60
            while not all(first(e, 7) and min((first(e, 3) - x) ** 2 + (first(e, 5) - z) ** 2 for x, z in SPAWNS) < 1
                          for e in c.entities.values() if first(e, 9) == 1):
                assert time.monotonic() < deadline, ("NPCs back at their spawns", c.entities)
                c.pump(0.2)
            while True:
                c.pump(0.05)
                me = c.entities[c.id]
                assert first(me, 7) and time.monotonic() < deadline, ("walk to the skill spot", me)
                if first(me, 6) < c.seq:
                    continue
                dx, dz = SKILL_SPOT[0] - first(me, 3), SKILL_SPOT[1] - first(me, 5)
                d = (dx * dx + dz * dz) ** .5
                if d < 0.3:
                    break
                c.move(dx / max(1, d), dz / max(1, d))
            c.move(0, 0)
            c.pump(0.3)
            c.logout()
            capture = out / "templates.ppm"
            capture.unlink(missing_ok=True)
            casts = []
            with open(out / "client.log", "w") as client_log:
                client = subprocess.Popen(
                    ["build/client/n3e-test-client", str(package), "--connect", f"localhost:{listen}", "--ca",
                     "deploy/local/ca.pem", "--auto-login", "--world-smoke", "14", "--capture", str(capture)],
                    env={**os.environ, "N3E_TEST_ACCOUNT": "caster", "N3E_TEST_PASSWORD": password,
                         "N3E_TEST_STAND_STILL": "1", "N3E_TEST_SHOWCASE_TARGET": "2.0",
                         "N3E_TEST_SHOWCASE_SKILL": "1.5 2;2.5 1;4.0 2;7.0 1 unchecked;8.0 3;9.0 4;10.0 0"},
                    stdout=client_log, stderr=subprocess.STDOUT)
                deadline = time.monotonic() + 120
                while client.poll() is None:
                    assert time.monotonic() < deadline, "graphical client timeout"
                    o.pump(0.1)
                    casts += [first(e, 26, b"").decode() for e in o.entities.values()
                              if first(e, 9) != 1 and first(e, 1) != o.id and first(e, 26, b"")]
                code = client.returncode
            o.logout()
            text = (out / "client.log").read_text()
            visible = [int(line.split("visible=")[1].split()[0]) for line in text.splitlines() if line.startswith("WORLD ")]
            assert code == 0 and visible and visible[-1] >= 3 and capture.stat().st_size > 0, (code, text[-1500:])
            print(f"PASS graphical client renders the N3N3 package: {visible[-1]} entities, {capture}", flush=True)
            import re
            chosen = re.search(r"^SHOWCASE_TARGET at=\S+ nearest=(\d+)$", text, re.M)
            refused = re.findall(r"^SKILL_TOO_FAR skill=(\S+) target=(\d+) distance=(\S+) limit=(\S+) notice='(.*)'$",
                                 text, re.M)
            sent = re.findall(r"^SKILL_SENT skill=(\S+) target=(\d+) seq=(\d+)( unchecked)?$", text, re.M)
            assert chosen and int(chosen[1]), text[-2000:]
            target = chosen[1]
            assert [(k, t) for k, t, *_ in refused] == [("demo:skill/bolt", target)], (refused, text[-2000:])
            distance, limit, notice = float(refused[0][2]), float(refused[0][3]), refused[0][4]
            assert limit == 3 and 6 < distance < 9 and notice == NOTICE.replace("%s", "Bolt"), refused
            assert f"NOTICE text='{notice}'" in text.splitlines(), text[-2000:]
            # The client's first action is the spark, its first sequence
            # number: the bolt took none (the client sent nothing for it).
            # PQ-469: the third press sends the bolt without the client's hint
            # (as a client that skips it would), as action 2.
            # PQ-481 (D-245): the spark pressed before the target was chosen
            # was held back (no action); the nova went out with no client level
            # test; the heal, pressed with the NPC selected, went to the caster.
            held = re.findall(r"^SKILL_HELD skill=(\S+) target=(\d+) reason=(\S+)$", text, re.M)
            assert held == [("demo:skill/spark", "0", "no_target")], (held, text[-2000:])
            # ... and posted no notice: no NOTICE line between that press and
            # the next showcase step (the bolt's too-far notice below shows the
            # harness prints each notice the client posts).
            lines = text.splitlines()
            press = next(i for i, line in enumerate(lines)
                         if line.startswith("SHOWCASE_SKILL ") and " index=2 target=0" in line)
            after = next((i for i in range(press + 1, len(lines)) if lines[i].startswith("SHOWCASE_")), len(lines))
            quiet = [line for line in lines[press + 1:after] if line.startswith("NOTICE ")]
            assert lines[press + 1:after] and not quiet, (quiet, lines[press:after])
            entered = re.search(r"^ENTERED map self=(\d+) ", text, re.M)
            assert entered, text[-2000:]
            caster = entered[1]
            assert sent == [("demo:skill/spark", target, "1", ""), ("demo:skill/bolt", target, "2", " unchecked"),
                            ("demo:skill/surge", target, "3", ""), ("demo:skill/nova", target, "4", ""),
                            ("demo:skill/heal", caster, "5", "")], \
                (sent, text[-2000:])
            # The server admitted the spark (another player sees it cast) and
            # never cast the bolt, the unchecked one included.
            assert {"demo:skill/spark", "demo:skill/heal"} <= set(casts) and \
                not {"demo:skill/bolt", "demo:skill/surge", "demo:skill/nova"} & set(casts), sorted(set(casts))
            print(f"PASS graphical client does not send a skill beyond its start limit (PQ-466): the bolt at "
                  f"{distance:.2f} m (limit {limit:g} m) posted '{notice}' and sent nothing (the spark went out "
                  f"as action 1); the spark at the same target (limit 27 m) was admitted and seen cast by another "
                  f"player", flush=True)
            # PQ-469 (D-235): the server refused the unchecked bolt
            # out_of_range on its own positions; the client posted the
            # policy's failed line for that one action only (not the spark),
            # in the policy's colour, and the HUD drew it so.
            # PQ-479 (D-243): the server refused the surge
            # insufficient_resource at its acceptance; the client posted the
            # policy's line for that status, in its colour, and drew it so.
            want = FAILED["text"].replace("%s", "Bolt")
            short = REFUSALS[0]["text"].replace("%s", "Surge")
            low = REFUSALS[2]["text"].replace("%s", "Nova")
            failed = re.findall(r"^SKILL_FAILED skill=(\S+) text='(.*)' color=([0-9a-f]{8})$", text, re.M)
            assert failed == [("demo:skill/bolt", want, f"{FAILED['color']:08x}"),
                              ("demo:skill/surge", short, f"{REFUSALS[0]['color']:08x}"),
                              ("demo:skill/nova", low, f"{REFUSALS[2]['color']:08x}")], (failed, text[-2000:])
            drawn = re.findall(r"^SKILL_FAILED_DRAWN text='(.*)' color=([0-9a-f]{8})$", text, re.M)
            assert drawn == [(want, f"{FAILED['color']:08x}"), (short, f"{REFUSALS[0]['color']:08x}"),
                             (low, f"{REFUSALS[2]['color']:08x}")], (drawn, text[-2000:])
            print(f"PASS graphical client posts the server's out_of_range refusal of a skill (PQ-469): the bolt "
                  f"sent without the client's hint was refused by the server and drew '{want}' in "
                  f"{FAILED['color']:08x}; no other action posted it", flush=True)
            print(f"PASS graphical client posts the policy's line for a refusal at the acceptance (PQ-479): the "
                  f"surge, refused insufficient_resource, drew '{short}' in {REFUSALS[0]['color']:08x}; the "
                  f"spark, admitted, posted nothing", flush=True)
            print(f"PASS graphical client picks a skill's recipient as 1298's skill start does (PQ-481): the "
                  f"spark with no target was held back (no action, no line); the nova above the caster's level "
                  f"was sent and the server's level_required drew '{low}'; the heal with the NPC selected went "
                  f"to the caster {caster} and was seen cast", flush=True)
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


def audit(p, sql, package, Budget, first):
    def npcs():
        return {first(e, 2).decode(): e for e in p.entities.values() if first(e, 9) == 1}

    def me():
        return p.entities[p.id]

    def distance(e):
        return ((first(e, 3) - first(me(), 3)) ** 2 + (first(e, 5) - first(me(), 5)) ** 2) ** .5

    def approach(target, within, budget):
        while budget.ok(p.entities):
            p.pump(0.1)
            e = npcs()[target]
            d = distance(e)
            if d <= within:
                p.move(0, 0)
                p.pump(0.15)
                return e
            budget.step()
            p.move((first(e, 3) - first(me(), 3)) / d, (first(e, 5) - first(me(), 5)) / d)
        raise AssertionError(("approach", target, budget.last))

    by_name = {t["name"]: t for t in TEMPLATES}
    drudge, brute = (t["name"] for t in TEMPLATES)
    # 1. Both templates in one view, each with its own name, looks, health and maximum.
    seen = npcs()
    assert set(seen) == set(by_name), seen.keys()
    for n, e in seen.items():
        t = by_name[n]
        got = (first(e, 31, b"").decode(), first(e, 7), first(e, 32))
        assert got == (t["looks"], t["health"], t["health"]), (n, got)
    print("PASS two N3N3 templates in one view: own name, looks key, health and max_health on the wire", flush=True)
    defense = first(p.stats, 2)
    assert first(p.stats, 5) > 0, p.stats
    print(f"player stats: defence {defense}, max health {first(p.stats, 5)}", flush=True)
    # 2. The passive drudge never acquires a player standing beside it.
    approach(drudge, 0.8, Budget("approach drudge", strikes=0, steps=400, guard=60))
    start = p.tick
    while p.tick - start < 80:
        p.pump(0.2)
        e = npcs()[drudge]
        assert first(e, 12) == b"idle" and first(e, 25) != p.id, ("passive drudge acquired", e)
    print("PASS passive template ignores a player beside it for 80 ticks", flush=True)
    strikes = {n: [] for n in by_name}  # (strike tick, result, damage) per template
    last = {n: first(e, 10) for n, e in npcs().items()}

    def watch():
        """Records each NPC strike on the player once and checks its damage
        against that NPC's own template attack."""
        for n, e in npcs().items():
            if first(e, 10) != last[n] and first(e, 25) == p.id:
                last[n] = first(e, 10)
                damage, result = first(e, 15), first(e, 14, b"").decode()
                lo, hi = strike_range(by_name[n]["attack"], defense)
                assert (result == "miss" and damage == 0) or (result == "hit" and lo <= damage <= hi), \
                    (n, damage, result, lo, hi)
                strikes[n].append((last[n], result, damage))

    def kill(target):
        """Kills one template and checks its own level and XP (solo, full credit)
        and the durable N3T1 settlement."""
        t = by_name[target]
        level = first(p.inventory, 5) or 1
        e = approach(target, 0.9, Budget("approach " + target, strikes=0, steps=600, guard=60))
        entity = first(e, 1)
        before = first(p.inventory, 4)
        budget = Budget("kill " + target, strikes=60, guard=120)
        killed = False
        while budget.ok(p.inventory, p.entities) and first(p.inventory, 4) == before:
            p.pump(0.1)
            watch()
            # A dead player cannot finish the kill, and the NPC it leaves heals
            # under a fresh identity: fail now, not at the stall guard (PQ-399).
            assert first(me(), 7) > 0, ("player killed during", target, budget.left, strikes, me())
            mine = [v for v in p.entities.values() if first(v, 1) == entity]
            killed = killed or any(first(v, 7) == 0 for v in mine)
            assert mine or killed, ("target left the view alive", target, entity, npcs().get(target))
            alive = [v for v in mine if first(v, 7) > 0]
            if alive and distance(alive[0]) <= 1.0:
                budget.result(p.action(entity))
            elif alive:
                budget.step()
                d = distance(alive[0])
                p.move((first(alive[0], 3) - first(me(), 3)) / d, (first(alive[0], 5) - first(me(), 5)) / d)
        gained = first(p.inventory, 4) - before
        d = t["level"] - level
        expected = t["xp"] if d < 2 else -(-t["xp"] * 6 // 5) if d < 5 else -(-t["xp"] * 3 // 2) if d < 8 else t["xp"] * 9 // 5
        assert gained == expected, (target, gained, expected, level)
        payload = sql(f"SELECT encode(payload,'hex') FROM encounter_settlements WHERE encounter={entity}")
        trailer = (b"N3T1" + struct.pack("<II", t["level"], t["xp"])).hex()
        assert payload.endswith(trailer), (target, payload[-40:], trailer)
        print(f"PASS {target} kill: {gained} XP from its template (level {t['level']}, XP {t['xp']}), "
              "settlement records the N3T1 reward", flush=True)

    def rest_to_full():
        """Sits (the package's rest policy) until the player's health is back at
        its maximum; the next action stands it up (rest.motion)."""
        from world_peer import integer
        top = first(p.stats, 5)
        budget = Budget("rest to full", strikes=0, steps=0, replies=8, guard=90)
        seq = 0
        p.move(0, 0)
        while first(me(), 7) < top and budget.ok(me()):
            p.pump(0.3)  # at least three ticks still after the last motion
            if first(me(), 21) != 1 and first(me(), 7) < top:
                budget.result("sit request")
                seq += 1
                p.send(45, integer(1, p.session) + integer(2, seq) + integer(3, p.id) + integer(4, 1))
        print(f"rested to full health: {first(me(), 7)}/{top}", flush=True)

    # 3. Kills award each template's own level and XP (solo, full credit). The
    # passive drudge first, from the full health the player still has beside it.
    kill(drudge)
    # 4. The aggressive brute acquires and strikes with its own attack value, then
    # dies; the player rests back to full first, out of the brute's search range.
    rest_to_full()
    fight = Budget("brute strikes", strikes=0, steps=600, guard=90)
    approach(brute, 5.5, fight)
    while len(strikes[brute]) < 2 and fight.ok(p.entities):
        p.pump(0.1)
        watch()
    # The template's attack delay (100 ticks), not the package's npc_cooldown_ticks (4).
    gap = strikes[brute][1][0] - strikes[brute][0][0]
    assert gap >= by_name[brute]["attack_ticks"], strikes[brute]
    print(f"PASS aggressive template strikes inside its own range {strike_range(by_name[brute]['attack'], defense)}"
          f" every {gap} ticks: {strikes[brute]}", flush=True)
    kill(brute)
    # The passive drudge struck back once hit, with its own (lower) attack.
    assert strikes[drudge], "the drudge never retaliated"
    print(f"PASS passive template retaliates inside its own range "
          f"{strike_range(by_name[drudge]['attack'], defense)}: {strikes[drudge]}", flush=True)
    # The realm's reward definition is still the package's progression policy.
    definition = sql("SELECT encode(definition,'hex') FROM active_reward_policy")
    import hashlib
    assert definition == hashlib.sha256((package / "progression.bin").read_bytes()).hexdigest(), definition
    # 5. A killed NPC respawns with its own template (60-tick slot respawn).
    respawned = Budget("respawn", strikes=0, steps=0, guard=30)
    while respawned.ok(p.entities):
        p.pump(0.2)
        alive = npcs()
        if all(first(alive.get(n, {}), 7) == by_name[n]["health"] for n in by_name) and len(alive) == 2:
            break
    for n, e in npcs().items():
        assert (first(e, 31, b"").decode(), first(e, 32)) == (by_name[n]["looks"], by_name[n]["health"]), (n, e)
    print("PASS both templates respawn with their own name, looks and health", flush=True)


if __name__ == "__main__":
    os.chdir(ROOT)
    package = prepare()
    check_readers(package)
    print("PASS N3N3 engine 37 package: both readers accept two templates", flush=True)
    live(package)
