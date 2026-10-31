"""PQ-315: the equipment glow on equipped appearance keys (N3E3), live.

The rule is the 2233 client's (a 2233/2145 addition; KO 1298 has none):
CPlayerBase::Tick (0057b3a0) calls 0056ea30 for every player, which keeps one
timer per player and writes the material emissive of each equipped part and
hand plug whose item asks for it (a pulse: t to 1 s, held to 3 s, falling to 0
at 5 s, restarting past 5.5 s; or a steady 1.0) and MODULATE or MODULATE2X,
which CN3CPart::Render (0042cf30) then draws. Evidence:
docs/implementation/evidence/pq-315-equipment-emissive-glow-2233.md.

The package is the PQ-272 fixture (tests/npc_scale_live.py) with an original
synthetic N3E3 effects file: no appearance effects, and a white pulse at 2x on
appearance key 1 (the blade in the right hand), whose geometry is replaced by
an upright grey quad lit at the ambient only, so the glow shows. The server knows nothing of
it: it projects appearance keys from committed equipment only.

Both readers must accept the package; the client must refuse a glow on an
appearance key the package does not have, and N3E3 files with a bad colour,
modulate, wave or timing, or trailing bytes. Against a native server on a
disposable Postgres and Redis two accounts equip the blade over the wire. With
N3E_GRAPHICAL=1 the real test client logs in as the first account while the
second stands 3 m ahead: it must draw the glow on both (EQUIPMENT_GLOW for
itself and for the other player), its sampled intensities must follow the
pulse on each player's own clock, it must end the other player's glow when
that player unequips and start it again on the re-equip. Both it and a second
client with Option.ini [Addition2233] EquipmentGlow=0 capture at 7.5 s (the
pulse's peak) and 10.75 s (its trough) of the local player's drawn time; each
pixel check compares captures of the same scene state (judge): the peak against
the option off at 7.5 s finds exactly the two blades, the peak beats the trough
at both blades (the pulse), and the trough beats the option off at 10.75 s at
both blades and nowhere else (the 2x, the pulse being 0 there).
"""
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tests") not in sys.path:
    sys.path.append(str(ROOT / "tests"))
from isolation import once_per_run  # noqa: E402
import appearance_effects_live as effects_live  # noqa: E402
import npc_looks_live  # noqa: E402

OUT = ROOT / "build/pq315"
# Seconds of the local player's clock: 7.5 % 5.5 = 2 (held at 1), 10.75 % 5.5 = 5.25 (0).
PEAK, TROUGH = 7.5, 10.75
AHEAD = effects_live.AHEAD


def glow(**change):
    g = dict(key=1, color=[1.0, 1.0, 1.0], modulate=2, wave=1, rise=1.0, hold=3.0, fall=5.0, period=5.5)
    g.update(change)
    return g


def n3e3(glows, keys=1):
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    import appearance_effects
    return appearance_effects.n3e3(effects_live.n3ef(), [], glows, keys)


GREY = 90


def detail():
    """The fixture's render detail (tests/npc_templates_live.py) with the blade's
    geometry as an upright quad beside the body, both windings, its normal
    pointing down so the light leaves it at the 0.35 ambient. The detail shader
    adds the fixture's white world slot as the second layer, so the quad's
    texel is white whatever its own grey, and the blade measures (PQ-315 round 2
    captures) 89 levels with the option off (0.35), 178 at the pulse's trough
    (2x alone, 0.7) and 255 at its peak (2x and the emissive, saturated)."""
    import render_detail

    def body(slot):
        return ([([x, 0, z], [0, 1, 0], [x, z], [0] * 4, [1, 0, 0, 0], slot) for x, z in [(0, 0), (1, 0), (0, 1)]],
                [0, 1, 2])

    def quad(slot):
        corners = [(.3, .2), (.9, .2), (.9, .8), (.3, .8)]
        vertices = [([x, y, 0], [0, -1, 0], [x, y], [0] * 4, [1, 0, 0, 0], slot) for x, y in corners]
        return vertices, [0, 1, 2, 0, 2, 3, 0, 2, 1, 0, 3, 2]
    white, grey = [(16, 16, bytes([255]) * 1024)], [(16, 16, bytes([GREY, GREY, GREY, 255]) * 256)]
    return render_detail.serialize(
        view=[1.134464, .5, 256], thresholds=[[6, 18, 32, 128]] * 4, workload=[30, 60, 100], world_count=1,
        textures=[white, white, grey], radius=1, levels=[body(1)] * 4, appearances=[([1], [quad(2)] * 4)])


@once_per_run
def prepare():
    """Cook the PQ-272 package with the N3E3 effects file; returns its directory."""
    from npc_scale_live import prepare as base
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    import main

    source = base().parent / "source"
    root, out = OUT / "source", OUT / "package"
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(source, root)
    m = json.loads((root / "package.json").read_text())
    assert m["appearance"] == [{"item": "demo:item/blade", "slot": 0}], m["appearance"]
    (root / "effects.bin").write_bytes(n3e3([glow()], len(m["appearance"])))
    (root / "detail.bin").write_bytes(detail())
    main.cook(root, out)
    return out.resolve()


def check_readers(package):
    npc_looks_live.check_readers(package)
    import struct
    bad = OUT / "hostile"
    good = n3e3([glow()])
    tail = 4 + 4 * 9  # the last glow record: key, colour, modulate, wave, timing
    record = lambda g: (struct.pack("<I3ffI4f", g["key"], *g["color"], g["modulate"], g["wave"],  # noqa: E731
                                    g["rise"], g["hold"], g["fall"], g["period"]))
    cases = [
        ("key", n3e3([glow(key=2)], 2), "appearance glow key"),
        ("colour", good[:-tail] + record(glow(color=[1.5, 1, 1])), "appearance glow colour"),
        ("modulate", good[:-tail] + record(glow(modulate=3)), "appearance glow modulate"),
        ("wave", good[:-tail] + record(glow(wave=2)), "cooked count"),
        ("timing", good[:-tail] + record(glow(hold=.5)), "appearance glow timing"),
        ("steady timing", good[:-tail] + record(glow(wave=0)), "appearance glow timing"),
        ("duplicate", good[:-tail - 4] + struct.pack("<I", 2) + record(glow()) + record(glow()),
         "duplicate appearance glow"),
        ("trailing", good + b"\0", "cooked trailing bytes"),
    ]
    for name, effects, reason in cases:
        effects_live.repack(package, bad, effects)
        p = subprocess.run(["build/client/n3e-asset-check", str(bad)], cwd=ROOT, capture_output=True, text=True)
        assert p.returncode != 0 and reason in p.stdout + p.stderr, (name, p.stdout[-400:], p.stderr[-400:])
    shutil.rmtree(bad)
    return len(cases)


def expected(t):
    c = math.fmod(t, 5.5)
    return c if c <= 1 else 1 if c <= 3 else 1 - (c - 3) * .5 if c <= 5 else 0


def brighter(a, b, levels=40):
    """Groups of pixels (joined across gaps up to 3 px) at least `levels`
    brighter, by channel sum / 3, in capture `a` than in `b`, in the middle rows,
    as (size, (x0, y0, x1, y1)), largest first."""
    width, height, pa = npc_looks_live.read_ppm(a)
    _, _, pb = npc_looks_live.read_ppm(b)
    mask = set()
    for y in range(height // 10, height * 9 // 10):
        for x in range(width):
            i = (y * width + x) * 3
            if sum(pa[i:i + 3]) - sum(pb[i:i + 3]) >= 3 * levels:
                mask.add((x, y))
    groups = []
    while mask:
        stack, members = [mask.pop()], []
        while stack:
            x, y = stack.pop()
            members.append((x, y))
            for dy in range(-3, 4):
                for dx in range(-3, 4):
                    if (x + dx, y + dy) in mask:
                        mask.remove((x + dx, y + dy))
                        stack.append((x + dx, y + dy))
        xs, ys = [m[0] for m in members], [m[1] for m in members]
        groups.append((len(members), (min(xs), min(ys), max(xs), max(ys))))
    return sorted(groups, reverse=True)


def overlap(a, b):
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def judge(on_peak, on_trough, off_peak, off_trough):
    """The three pixel checks, each between captures of the same scene state:
    the blades are where the peak beats the option-off capture of the same
    clock time (exactly two groups, the local and the other player's); the
    pulse is the peak beating the trough at both blades (other groups there are
    the scene moving between 7.5 s and 10.75 s and are not counted); the 2x is
    the trough (pulse 0) beating the option-off capture at 10.75 s by 20
    levels at both blades and nowhere else. Returns (failures, report)."""
    found = [g for g in brighter(on_peak, off_peak) if g[0] >= 30]
    blades = [box for _, box in found]
    pulse = [g for g in brighter(on_peak, on_trough) if g[0] >= 30]
    doubled = [g for g in brighter(on_trough, off_trough, levels=20) if g[0] >= 30]
    at = lambda groups, box: [g[0] for g in groups if overlap(g[1], box)]  # noqa: E731
    failures = []
    if len(blades) != 2 or overlap(*blades):
        failures.append(("blades", found))
    if not blades or not all(at(pulse, box) for box in blades):
        failures.append(("pulse", pulse))
    if len(doubled) != len(blades) or not blades or not all(at(doubled, box) for box in blades):
        failures.append(("2x", doubled))
    report = dict(blades=found, pulse=[at(pulse, box) for box in blades], doubled=doubled)
    return failures, report


def live(package):
    from isolation import DISPOSABLE_POSTGRES, container_logs, free_ports
    from readiness import wait_postgres
    from world_peer import Peer, blob, fields, first, integer
    import urllib.request

    manifest = json.loads((package / "recipe.json").read_text())["manifest"]
    out = OUT / "live"
    out.mkdir(parents=True, exist_ok=True)
    server_binary = str(Path(os.environ.get("N3E_TEST_SERVER", "target/debug/n3e-server")).resolve())
    name = "n3e-pq315-" + uuid.uuid4().hex[:10]
    passwords = {account: "test-only-" + uuid.uuid4().hex for account in ("explorer", "companion")}
    containers, server, log = [], None, None

    def run(*cmd, env=None, stdin=None):
        p = subprocess.run(cmd, env=env, input=stdin, capture_output=True, text=True, timeout=120)
        assert p.returncode == 0, (cmd, p.returncode, p.stdout, p.stderr)
        return p.stdout

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
        p.send(32, integer(1, op) + blob(2, f"pq315-{serial[0]}") + integer(3, first(state, 1)) + integer(4, source)
               + integer(5, destination) + integer(6, first(fields(records[source]), 1)))
        d = wait(p, 33)
        assert first(d, 2) == b"committed", d
        return fields(first(d, 3))

    def keys(p, entity):
        return list(first(p.entities.get(entity, {}), 20, b""))

    def walk(p, x, z):
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

        def peer(account):
            p = Peer(listen, account, passwords[account], content=(package / "release.sha256").read_text().strip(),
                     game=manifest["game_id"], protocol=manifest["protocol_version"])
            p.create(account.title())
            assert p.select(p.characters[0][0])[0] == 10
            return p
        a = peer("explorer")
        state = bag(a)
        assert first(fields(state[5][0]), 2) == b"demo:item/blade", state[5][0]
        bag(a, 5, 0, 0, state)
        wait(a, 10, lambda _: keys(a, a.id) == [1])
        a.logout()
        b = peer("companion")
        b_state = bag(b, 5, 0, 0, bag(b))
        wait(b, 10, lambda _: keys(b, b.id) == [1])
        walk(b, *AHEAD)
        print(f"PASS both accounts equip the blade over the wire and carry appearance key 1; the companion "
              f"stands at {AHEAD}", flush=True)
        if os.environ.get("N3E_GRAPHICAL") != "1":
            b.logout()
            return

        def client(capture, config, steps=()):
            lines = []
            proc = subprocess.Popen(
                ["build/client/n3e-test-client", str(package), "--connect", f"localhost:{listen}", "--ca",
                 "deploy/local/ca.pem", "--auto-login", "--world-smoke", "14", "--capture", str(capture)],
                env={**os.environ, "N3E_TEST_ACCOUNT": "explorer", "N3E_TEST_PASSWORD": passwords["explorer"],
                     "N3E_TEST_EQUIPMENT_GLOW": "1", "N3E_TEST_EQUIPMENT_GLOW_CAPTURES": f"{PEAK},{TROUGH}",
                     "XDG_CONFIG_HOME": config},
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            reader = threading.Thread(target=lambda: lines.extend(proc.stdout), daemon=True)
            reader.start()
            pending = list(steps)
            while proc.poll() is None:
                b.pump(.1)
                if pending and pending[0][0]("".join(lines)):
                    pending.pop(0)[1]()
            reader.join(10)
            text = "".join(lines)
            capture.with_suffix(".log").write_text(text)
            assert proc.returncode == 0, (proc.returncode, text[-1500:])
            assert not pending, ("steps not reached", len(pending), text[-1500:])
            made = re.findall(r"^EQUIPMENT_GLOW_CAPTURE at=([0-9.]+) drawn=[0-9.e+-]+ path=(.+)$", text, re.M)
            assert [float(t) for t, _ in made] == [PEAK, TROUGH], (made, text[-1500:])
            return text, [Path(p) for _, p in made]
        held = {}

        def unequip():
            held["state"] = bag(b, 6, 0, 0, b_state)
            wait(b, 10, lambda _: keys(b, b.id) == [])

        def equip():
            bag(b, 5, 0, 0, held["state"])
            wait(b, 10, lambda _: keys(b, b.id) == [1])

        def found(*patterns):
            return lambda text: all(re.search(p, text, re.M) for p in patterns)
        other = b.id
        start = r"^EQUIPMENT_GLOW entity={} self={} key=1 wave=pulse modulate=2 color=1,1,1 vertices=\d+$"
        with tempfile.TemporaryDirectory(dir=OUT) as config:
            text, shown = client(out / "glow-on.ppm", config, steps=[
                (found(start.format(r"\d+", 1), start.format(other, 0)), unequip),
                (found(rf"^EQUIPMENT_GLOW_END entity={other} key=1$"), equip)])
            assert "a 2233/2145 addition (N3E3), on" in text, text[:1500]
            mine = re.findall(start.format(r"\d+", 1), text, re.M)
            others = re.findall(start.format(other, 0), text, re.M)
            ended = re.findall(rf"^EQUIPMENT_GLOW_END entity={other} key=1$", text, re.M)
            assert len(mine) == 1 and len(others) == 2 and len(ended) == 1, (mine, others, ended, text[-2000:])
            samples = [(int(e), float(t), float(i)) for e, t, i in re.findall(
                r"^EQUIPMENT_GLOW_SAMPLE entity=(\d+) key=1 t=([0-9.e+-]+) intensity=([0-9.e+-]+)$", text, re.M)]
            assert samples and all(abs(i - expected(t)) < 1e-3 for _, t, i in samples), samples
            assert {e for e, _, _ in samples} >= {other} and len({e for e, _, _ in samples}) == 2, samples
            phases = {"rise" if c < 1 else "hold" if c <= 3 else "fall" if c < 5 else "off"
                      for e, t, _ in samples if e != other for c in [math.fmod(t, 5.5)]}
            assert {"rise", "hold", "fall"} <= phases, (phases, samples)
            print(f"PASS the client draws the glow on itself and on the other player, ends the other's on its "
                  f"unequip and starts it again on its re-equip; {len(samples)} intensity samples follow the "
                  f"pulse through {sorted(phases)} on each player's clock", flush=True)
            Path(config, "n3e").mkdir()
            Path(config, "n3e", "Option.ini").write_text("[Addition2233]\nEquipmentGlow=0\n")
            quiet, hidden = client(out / "glow-off.ppm", config)
            assert "EQUIPMENT_GLOW " not in quiet and "off by Option.ini" in quiet, quiet[-1500:]
        # Blade levels measured: about 89 off, 178 at the trough (2x alone), 255
        # at the peak; so the peak beats both, and the trough beats off by 89.
        failures, report = judge(shown[0], shown[1], hidden[0], hidden[1])
        assert not failures, (failures, report)
        print(f"PASS graphical client draws the equipment glow on the local and the other player: blades "
              f"{[g[0] for g in report['blades']]} px brighter at the peak than EquipmentGlow=0 at 7.5 s; peak over "
              f"trough at the blades {report['pulse']} px; trough (2x alone) over EquipmentGlow=0 at 10.75 s by 20 "
              f"levels {[g[0] for g in report['doubled']]} px, at the blades only; {shown[0]}, {shown[1]}, "
              f"{hidden[0]}, {hidden[1]}", flush=True)
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
    assert (package / "effects.bin").read_bytes()[:4] == b"N3E3"
    refused = check_readers(package)
    print(f"PASS N3E3 package: both readers accept it; the client refuses {refused} malformed glow files", flush=True)
    live(package)
