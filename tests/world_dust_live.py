"""RQ-203 (Q120): the world's dust overlay on worn items (N3E6), live.

KO's world durability setter (1298 0045d5f0, 1097 004535a0; the source's
CPlayerBase::DurabilitySet) sets Misc\\Dust_Hard.dxt on a worn hand plug or
armour part below 31 % of its item's durability and Misc\\Dust_Soft.dxt below
71 %, for the local player and for every other player it draws (the source's
CPlayerOther init and MsgRecv_UserLookChange call it with the server's
durability); the part and plug draws then modulate the lit colour by the
overlay (00412570, 004137d0; specs/KO-FINDINGS.md 8.6).

The package is the PQ-315 fixture (tests/equipment_glow_live.py: the PQ-272
package with appearance key 1, the blade in the right hand, drawn as an
upright grey quad lit at the ambient alone, about 89 levels) with an original
synthetic N3E6 effects file: no effects or glow, two dust textures of flat
grey (64, hard; 128, soft) and the dust on key 1; the blade's maximum
durability is 100. The server knows nothing of the dust: it carries each
key's durability percent from committed equipment (Entity.appearance_durability).

Both readers must accept the package, and the client must refuse dust on a
key the package does not have. Against a native server on a disposable
Postgres and Redis two accounts equip the blade over the wire; with each
character offline, its equipped blade is set to 20 (the explorer) and 50 (the
companion) of 100 in its committed bag, and each then carries percent 20 and
50 on key 1 to every viewer. With N3E_GRAPHICAL=1 the real test client logs in
as the explorer while the companion stands 3 m ahead: it must draw the hard
dust on itself and the soft on the companion (WORLD_DUST); against a second
client drawing no dust (N3E_TEST_WORLD_DUST=ignore) captured at the same drawn
time, the dust capture must be darker at exactly the two blades and nowhere
else, the hard-dusted blade by more than the soft.
"""
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tests") not in sys.path:
    sys.path.append(str(ROOT / "tests"))
from isolation import once_per_run  # noqa: E402
import appearance_effects_live as effects_live  # noqa: E402
import equipment_glow_live as glow_live  # noqa: E402
import npc_looks_live  # noqa: E402

OUT = ROOT / "build/rq203"
HARD, SOFT = 64, 128  # the synthetic dust textures' grey levels
PERCENT = {"explorer": 20, "companion": 50}
CAPTURE = 7.5  # seconds of the local player's drawn time (PQ-315's peak capture: both blades in view)


def n3ef():
    """PQ-211's synthetic N3EF with the two dust textures after its five."""
    data = effects_live.n3ef()
    count, at = struct.unpack_from("<I", data, 4)[0], 8
    for _ in range(count):
        w, h = struct.unpack_from("<2I", data, at)
        at += 8 + w * h * 4
    flat = lambda level: struct.pack("<2I", 4, 4) + bytes([level, level, level, 255]) * 16  # noqa: E731
    return b"N3EF" + struct.pack("<I", count + 2) + data[8:at] + flat(HARD) + flat(SOFT) + data[at:], count


def n3e6(keys=(1,), key_count=1):
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    import appearance_effects
    data, first = n3ef()
    return appearance_effects.n3e6(data, [], [], [], [], dict(hard=first, soft=first + 1, keys=list(keys)), key_count)


@once_per_run
def prepare():
    """Cook the PQ-315 package's source with the N3E6 effects file and a blade
    of maximum durability 100; returns its directory."""
    source = glow_live.prepare().parent / "source"
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    import main

    root, out = OUT / "source", OUT / "package"
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(source, root)
    m = json.loads((root / "package.json").read_text())
    assert m["appearance"] == [{"item": "demo:item/blade", "slot": 0}], m["appearance"]
    for item in m["inventory"]["items"] + m["progression"]["items"]["items"]:
        if item["id"] == "demo:item/blade":
            item["durability"] = 100
    (root / "package.json").write_text(json.dumps(m))
    (root / "effects.bin").write_bytes(n3e6())
    main.cook(root, out)
    return out.resolve()


def check_readers(package):
    npc_looks_live.check_readers(package)
    bad = OUT / "hostile"
    effects_live.repack(package, bad, n3e6(keys=(2,), key_count=2))
    p = subprocess.run(["build/client/n3e-asset-check", str(bad)], cwd=ROOT, capture_output=True, text=True)
    assert p.returncode != 0 and "appearance dust key" in p.stdout + p.stderr, (p.stdout[-400:], p.stderr[-400:])
    shutil.rmtree(bad)


def darker(with_dust, without, box, levels=20):
    """The pixels inside `box` at least `levels` darker (channel sum / 3) in
    `with_dust` than in `without`, and their mean drop."""
    width, height, a = npc_looks_live.read_ppm(with_dust)
    _, _, b = npc_looks_live.read_ppm(without)
    drops = []
    x0, y0, x1, y1 = box
    for y in range(max(0, y0), min(height, y1 + 1)):
        for x in range(max(0, x0), min(width, x1 + 1)):
            i = (y * width + x) * 3
            drop = (sum(b[i:i + 3]) - sum(a[i:i + 3])) / 3
            if drop >= levels:
                drops.append(drop)
    return len(drops), (sum(drops) / len(drops) if drops else 0)


def judge(with_dust, without, boxes):
    """The darkening between the dust capture and the capture without it at the
    same drawn time: groups at least 20 levels darker are exactly the two
    blades, one on each player's dust box, and the hard one's mean drop is
    above the soft one's. Returns (failures, report)."""
    found = [g for g in glow_live.brighter(without, with_dust, levels=20) if g[0] >= 30]
    failures = []
    if len(found) != 2 or sorted(sum(glow_live.overlap(g[1], box) for g in found) for box in boxes.values()) != [1, 1]:
        failures.append(("blades", found, boxes))
    drops = {who: darker(with_dust, without, box) for who, box in boxes.items()}
    if not drops["self"][0] or not drops["other"][0] or not drops["self"][1] > drops["other"][1] + 10:
        failures.append(("hard over soft", drops))
    return failures, dict(found=found, drops=drops)


def live(package):
    from isolation import DISPOSABLE_POSTGRES, container_logs, free_ports
    from readiness import wait_postgres
    from world_peer import Peer, blob, fields, first, integer
    import urllib.request

    manifest = json.loads((package / "recipe.json").read_text())["manifest"]
    out = OUT / "live"
    out.mkdir(parents=True, exist_ok=True)
    server_binary = str(Path(os.environ.get("N3E_TEST_SERVER", "target/debug/n3e-server")).resolve())
    name = "n3e-rq203-" + uuid.uuid4().hex[:10]
    passwords = {account: "test-only-" + uuid.uuid4().hex for account in ("explorer", "companion")}
    containers, server, log = [], None, None

    def run(*cmd, env=None, stdin=None):
        p = subprocess.run(cmd, env=env, input=stdin, capture_output=True, text=True, timeout=120)
        assert p.returncode == 0, (cmd, p.returncode, p.stdout, p.stderr)
        return p.stdout

    def sql(query):
        return run("docker", "exec", name, "psql", "-U", "n3e", "-d", "n3e", "-Atc", query).strip()

    def encode(data):
        return b"".join((integer(k, v) if isinstance(v, int) else blob(k, v))
                        for k, vs in sorted(data.items()) for v in vs)

    serial = [0]

    def wait(p, tag, predicate=lambda d: True, seconds=8):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            t, d = p.receive()
            assert t != 4, (t, d)
            if t == tag and predicate(d):
                return d
        raise AssertionError(("timeout", tag))

    def bag(p, op=0, source=0, destination=0, state=None):
        time.sleep(.22)  # inside the shared inventory request budget
        if not op:
            p.send(32, b"")
            return fields(first(wait(p, 33, lambda d: first(d, 2) == b"ok"), 3))
        serial[0] += 1
        records = state[6] if op == 6 else state[5]
        p.send(32, integer(1, op) + blob(2, f"rq203-{serial[0]}") + integer(3, first(state, 1)) + integer(4, source)
               + integer(5, destination) + integer(6, first(fields(records[source]), 1)))
        d = wait(p, 33)
        assert first(d, 2) == b"committed", d
        return fields(first(d, 3))

    def worn(p, entity):
        """Entity `entity`'s appearance keys and durability percents as `p` sees it."""
        e = p.entities.get(entity, {})
        return list(first(e, 20, b"")), list(first(e, 34, b""))

    def wear(account, percent):
        """With `account`'s character offline: its equipped blade (slot 0) at
        `percent` of 100 in its committed bag (test-only SQL on a disposable realm)."""
        character = account.title()
        state = fields(bytes.fromhex(sql(
            "SELECT encode(b.state,'hex') FROM character_bags b JOIN characters c ON c.id=b.character_id "
            f"WHERE c.name='{character}'")))
        item = fields(state[6][0])
        assert first(item, 2) == b"demo:item/blade", item
        item[4] = [percent]
        state[6][0] = encode(item)
        state[1] = [first(state, 1) + 1]
        sql("UPDATE character_bags b SET state=decode('" + encode(state).hex() + "','hex') FROM characters c "
            f"WHERE b.character_id=c.id AND c.name='{character}'")

    def walk(p, x, z):
        import math
        end = time.monotonic() + 30
        while time.monotonic() < end:
            p.pump(.05)
            me = p.entities[p.id]
            if first(me, 6) < p.seq:
                continue
            dx, dz = x - first(me, 3), z - first(me, 5)
            d = math.hypot(dx, dz)
            if d < .3:
                p.move(0, 0)
                p.pump(.2)
                return
            p.move(dx / max(1, d), dz / max(1, d), mode=1)
        raise AssertionError(("blocked", x, z, p.entities[p.id]))

    try:
        for suffix, image, port, extra in [
            ("", npc_looks_live.POSTGRES, 5432, ["-e", "POSTGRES_USER=n3e", "-e", "POSTGRES_PASSWORD=test-only",
                                                 "-e", "POSTGRES_DB=n3e", *DISPOSABLE_POSTGRES]),
            ("-redis", npc_looks_live.REDIS, 6379, []),
        ]:
            run("docker", "run", "--rm", "-d", "--name", name + suffix, *extra, "-p", f"127.0.0.1::{port}", image)
            containers.append(name + suffix)
        pg = wait_postgres(name)
        redis = run("docker", "port", name + "-redis", "6379").split()[0]
        listen, health = free_ports(2)
        env = dict(os.environ, DATABASE_URL=f"host=127.0.0.1 port={pg} user=n3e password=test-only dbname=n3e",
                   REDIS_ADDRESS=redis, N3E_PACKAGE=str(package), N3E_REALM="test-" + name,
                   N3E_LISTEN=f"127.0.0.1:{listen}", N3E_HEALTH=f"127.0.0.1:{health}")
        run(server_binary, "migrate", env=env)
        run(server_binary, "convert-progression", env={**env, "N3E_TEST_PROGRESSION": "disposable"})
        for account, password in passwords.items():
            run(server_binary, "account-create", account, env=env, stdin=password + "\n")
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

        def peer(account, create=False):
            p = Peer(listen, account, passwords[account], content=(package / "release.sha256").read_text().strip(),
                     game=manifest["game_id"], protocol=manifest["protocol_version"])
            if create:
                p.create(account.title())
            assert p.select(p.characters[0][0])[0] == 10
            return p
        for account in ("explorer", "companion"):
            p = peer(account, create=True)
            state = bag(p)
            assert first(fields(state[5][0]), 2) == b"demo:item/blade", state[5][0]
            full = first(fields(bag(p, 5, 0, 0, state)[6][0]), 4)
            # As granted: the percent of the blade's 100 (100 at full durability).
            wait(p, 10, lambda _: worn(p, p.id) == ([1], [min(100, full)]))
            p.logout()
            wear(account, PERCENT[account])
        b = peer("companion")
        wait(b, 10, lambda _: worn(b, b.id) == ([1], [PERCENT["companion"]]))
        walk(b, *effects_live.AHEAD)
        a = peer("explorer")
        wait(a, 10, lambda _: worn(a, a.id) == ([1], [PERCENT["explorer"]])
             and worn(a, b.id) == ([1], [PERCENT["companion"]]))
        a.logout()
        print(f"PASS each player carries its blade's durability percent on key 1 to every viewer "
              f"(explorer {PERCENT['explorer']}, companion {PERCENT['companion']}, 100 at full durability); "
              f"the companion stands at {effects_live.AHEAD}", flush=True)
        if os.environ.get("N3E_GRAPHICAL") != "1":
            b.logout()
            return

        def client(capture, mode):
            lines = []
            proc = subprocess.Popen(
                ["build/client/n3e-test-client", str(package), "--connect", f"localhost:{listen}", "--ca",
                 "deploy/local/ca.pem", "--auto-login", "--world-smoke", "12", "--capture", str(capture)],
                env={**os.environ, "N3E_TEST_ACCOUNT": "explorer", "N3E_TEST_PASSWORD": passwords["explorer"],
                     "N3E_TEST_WORLD_DUST": mode, "N3E_TEST_EQUIPMENT_GLOW_CAPTURES": str(CAPTURE),
                     "N3E_TEST_STAND_STILL": "1",
                     "XDG_CONFIG_HOME": str(out)},
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            reader = threading.Thread(target=lambda: lines.extend(proc.stdout), daemon=True)
            reader.start()
            while proc.poll() is None:
                b.pump(.1)
            reader.join(10)
            text = "".join(lines)
            capture.with_suffix(".log").write_text(text)
            assert proc.returncode == 0, (proc.returncode, text[-1500:])
            assert "world dust: 1 key(s) (N3E6)" in text, text[:1500]
            # Either way the client decides the same dust for each player.
            mine = re.findall(r"^WORLD_DUST entity=(\d+) self=1 key=1 percent=(\d+) dust=(\w+)$", text, re.M)
            others = re.findall(rf"^WORLD_DUST entity={b.id} self=0 key=1 percent=(\d+) dust=(\w+)$", text, re.M)
            assert [m[1:] for m in mine] == [(str(PERCENT["explorer"]), "hard")], (mine, text[-2000:])
            assert others == [(str(PERCENT["companion"]), "soft")], (others, text[-2000:])
            made = re.findall(r"^EQUIPMENT_GLOW_CAPTURE at=([0-9.]+) drawn=[0-9.e+-]+ path=(.+)$", text, re.M)
            assert [float(t) for t, _ in made] == [CAPTURE], (made, text[-1500:])
            boxes = {}
            for _, is_self, box in re.findall(
                    r"^WORLD_DUST_BOX at=[0-9.]+ entity=(\d+) self=(\d) key=1 box=(\S+)$", text, re.M):
                boxes["self" if is_self == "1" else "other"] = tuple(int(v) for v in box.split(","))
            assert set(boxes) == {"self", "other"}, (boxes, text[-1500:])
            return Path(made[0][1]), boxes
        shown, boxes = client(out / "dust.ppm", "1")
        print("PASS the client draws the hard dust on itself (20 %) and the soft on the other player (50 %)",
              flush=True)
        hidden, _ = client(out / "ignored.ppm", "ignore")
        failures, report = judge(shown, hidden, boxes)
        assert not failures, (failures, report)
        print(f"PASS graphical client draws the dust on the local and the other player: darker than the capture "
              f"without it at exactly the two blades {[g[0] for g in report['found']]} px; mean drop "
              f"{report['drops']['self'][1]:.0f} levels under the hard dust, {report['drops']['other'][1]:.0f} "
              f"under the soft; {shown}, {hidden}", flush=True)
        b.logout()
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


if __name__ == "__main__":
    os.chdir(ROOT)
    package = prepare()
    assert (package / "effects.bin").read_bytes()[:4] == b"N3E6"
    check_readers(package)
    print("PASS N3E6 package: both readers accept it; the client refuses dust on a key the package does not have",
          flush=True)
    live(package)
