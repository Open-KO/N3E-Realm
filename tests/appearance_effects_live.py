"""PQ-211: effects on equipped appearance keys (N3E2; N3E5 since PQ-376), live.

KO draws an equipped weapon's effect on the hand plug for the local player and
for every other player in view: the plug setter 0045c6e0 serves the local
player's MyInfo slots (005c87c0), players coming into view (0046dcb0 from the
user-in 005cbd70) and another player's gear change (005cfe60); the plug draw
004158d0 calls 00415910 only while Option.Ini WeaponEffect.EffectVisible is set
(0064b9b0, default 1). evidence/pq-211-hand-item-effects.md labels each claim.

The package is the PQ-272 fixture (tests/npc_scale_live.py) with an original
synthetic N3E5 effects file: appearance key 1 (the blade in the right hand)
carries a magenta glow, three copies of a cross of quads beside the body with
a three-frame texture sequence and the jitter, two cyan tails and a sort record
(PQ-376, D-200: 1298's alpha-list keys, 00415910 and 004840b0). The server
knows nothing of it: it projects appearance keys from committed equipment only.

Both readers must accept the package, and the client must refuse an effect on
an appearance key the package does not have and one on a joint its skeleton
does not have. Against a native server on a disposable Postgres and Redis two
accounts equip the blade over the wire, and the other player's entity carries
key 1. With N3E_GRAPHICAL=1 the real test client logs in as the first account
while the second stands 3 m ahead and to the left: it must draw the effect on
both (an APPEARANCE_EFFECT line for itself and for the other player, three
copies, two tails, the trail colour), end the other player's effect when that
player unequips (APPEARANCE_EFFECT_END) and start it again when the blade comes
back, and the capture must show the magenta glow on two players and the cyan tails.
The tail box lies inside the glow again (PQ-370's old placement) and the glow is
opaque, so a spark shows only where the effect pass draws it after the glow
copies over it: with the sort record each spark sorts on its own, nearer than
the copies, and every measured frame (N3E_TEST_EFFECT_PIXELS, after the effect
pass) must hold cyan pixels. The suite first checks, at the eye the client
reports, that the fixture separates the keys: each spark nearer than every
copy's biased key, every link's newest point (n3e's old one key per link)
farther, and every copy's unbiased key nearer than the sparks. So keeping one
key per link, or dropping the bias, puts the glow over every spark.
A second client with an Option.ini that sets WeaponEffect.EffectVisible=0
draws none of it. N3E_TEST_STAND_STILL holds the world smoke's player still
(PQ-357): walking, it ended each run somewhere else, and where its glow lined
up with the other player's the two merged into one cluster. The companion
watches the explorer through each client run, and one that moves fails the
suite before any pixel is read.
"""
import json
import os
from pathlib import Path
import re
import shutil
import struct
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
import npc_looks_live  # noqa: E402

OUT = ROOT / "build/pq211"
MAGENTA = [(255, 0, 255), (235, 0, 235), (215, 0, 215)]
CYAN = (0, 255, 255)
TRACE = 0xffffff00
# The other player stands 3 m ahead of the spawn and 1.5 m to its left, between
# the camera and the PQ-272 pillars (z -12), so both players are in the capture.
# The explorer stands still at the spawn, facing as the other player does, so
# straight ahead the two right-hand glows line up on screen and merge into one
# cluster (PQ-357); 1.5 m to the left keeps them apart.
AHEAD = (-6.5, -8.0)
# PQ-370 moved the tail box beside the glow: the effect pass then sorted each
# tail link and glow copy by one point, so inside the glow's footprint a spark
# showed only when its link sorted nearer than all three copies (21 of 1592
# frames held no cyan). PQ-376 puts it back inside the glow (x 0.35-0.75, y
# 0.2-1.6), its old placement: KO's per-spark and per-copy keys decide.
TAIL_BOX = [[.35, .2, 0], [.75, .2, 0], [.35, 1.6, 0], [.35, .2, .1]]
# The glow: crosses of half width 0.45 from y 0.05 to 1.6, wide enough to cover
# every spark on screen for both players.
GLOW = dict(half=.45, low=.05, high=1.6)
# Each spark stands 1 m from its box point toward the camera (world, roughly
# along the eye ray from both players, who face -z with the camera behind):
# nearly the same screen point, 1 m nearer. The copies sort at the glow's
# centre moved 1.6 m that way, plus a bias of 1.07 m: between the sparks and
# the box points, which n3e's old link key used (heading 0: model = world axes).
TOWARD = [0, .399 / (.399 ** 2 + .917 ** 2) ** .5, .917 / (.399 ** 2 + .917 ** 2) ** .5]
SPARK_LIFT, SORT_LIFT, SORT_BIAS = 1.0, 1.6, 1.07
SORT = dict(key=1, origin=[.55 + SORT_LIFT * TOWARD[0], .9 + SORT_LIFT * TOWARD[1], SORT_LIFT * TOWARD[2]],
            bias=SORT_BIAS)
# The suite's cyan: g > 150, b > 150, r < 90 (clusters()), as the client counts it.
CYAN_RANGE = "0,89,151,255,151,255"


def u(*v):
    return struct.pack("<%dI" % len(v), *v)


def fl(*v):
    return struct.pack("<%df" % len(v), *v)


def string(s):
    return u(len(s)) + s.encode()


def n3ef():
    """Textures (0: blank, 1-3: the glow frames, 4: the tail spark), the skill's
    two blank clips and a two-second tail clip: one spark born each 1/30 s,
    SPARK_LIFT m from the link's anchor toward the camera, living nine frames."""
    def texture(rgb):
        return u(4, 4) + bytes([*rgb, 255]) * 16
    data = b"N3EF" + u(5) + u(1, 1) + bytes(4) + b"".join(texture(c) for c in MAGENTA) + texture(CYAN)
    blank = lambda name: string(name) + u(0) + u(10) + u(1) + u(0)  # noqa: E731
    tail = string("spark") + u(0) + u(30) + u(60)
    for frame in range(60):
        born = range(max(0, frame - 8), frame + 1)
        tail += u(1) + u(1, 4, 5, 6, 455, len(born))
        tail += b"".join(fl(*(SPARK_LIFT * t for t in TOWARD), .12, .12, 0, 1, 1, 1, 1, k / 30) for k in born)
    return data + u(3) + blank("cast") + blank("heal") + tail + u(0)


def cross(x, y0, y1, half=.2):
    """Two upright quads crossed at (x, 0), so the glow shows from any heading."""
    out = []
    for a, b in (((x - half, 0), (x + half, 0)), ((x, -half), (x, half))):
        corners = [(*a, y0, 0, 0), (*b, y0, 1, 0), (*b, y1, 1, 1), (*a, y1, 0, 1)]
        out += [[cx, cy, cz, s, t] for cx, cz, cy, s, t in (corners[i] for i in (0, 1, 2, 0, 2, 3))]
    return out


def entry(**change):
    e = dict(key=1, joint=0, frames=[1, 2, 3], fps=10, phase_steps=1000, phase_step=.01, blend=[5, 6], flags=455,
             copies=[dict(jitter=0, frame_offset=0, vertices=cross(.55, GLOW["low"], GLOW["high"], GLOW["half"])),
                     dict(jitter=1, frame_offset=1, vertices=cross(.57, GLOW["low"], GLOW["high"], GLOW["half"])),
                     dict(jitter=-1, frame_offset=2, vertices=cross(.53, GLOW["low"], GLOW["high"], GLOW["half"]))],
             jitter_rate=1.2, jitter_amplitude=.035, jitter=[[0, 0, 0], [0, 0, 1]],
             tail_box=TAIL_BOX,
             tail_low=.25, tail_steps=50, tail_step=.01, tails=2, tail_clip="spark", trace_color=TRACE)
    e.update(change)
    return e


@once_per_run
def prepare():
    """Cook the PQ-272 package with the N3E5 effects file; returns its directory."""
    from npc_scale_live import prepare as base
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    import appearance_effects
    import main

    source = base().parent / "source"
    root, out = OUT / "source", OUT / "package"
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(source, root)
    m = json.loads((root / "package.json").read_text())
    assert m["appearance"] == [{"item": "demo:item/blade", "slot": 0}], m["appearance"]
    (root / "effects.bin").write_bytes(appearance_effects.n3e5(n3ef(), [entry()], [], [], [SORT],
                                                               len(m["appearance"])))
    main.cook(root, out)
    return out.resolve()


def repack(package, out, effects):
    """A copy of `package` whose effects.bin is `effects`, rehashed into release.bin."""
    import hashlib
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(package, out)
    (out / "effects.bin").write_bytes(effects)
    m = json.loads((out / "recipe.json").read_text())["manifest"]
    names = sorted(p.name for p in out.iterdir() if p.name not in ("release.bin", "release.sha256"))
    index = b"N3R1" + u(1, m["engine_version"], m["protocol_version"]) + string(m["game_id"]) \
        + string(m["package_version"]) + u(len(names))
    for name in names:
        data = (out / name).read_bytes()
        index += string(name) + u(len(data)) + hashlib.sha256(data).digest()
    (out / "release.bin").write_bytes(index)


def check_readers(package):
    npc_looks_live.check_readers(package)
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    import appearance_effects
    bad = OUT / "hostile"
    # An effect on a key past the package's one appearance, and one on a joint
    # the skeleton lacks: the serializer is told of two keys so it writes them.
    for name, effects, reason in [
            ("key", appearance_effects.n3e2(n3ef(), [entry(key=2)], 2), "appearance effect key"),
            ("joint", appearance_effects.n3e2(n3ef(), [entry(joint=200)], 1), "appearance effect joint")]:
        repack(package, bad, effects)
        p = subprocess.run(["build/client/n3e-asset-check", str(bad)], cwd=ROOT, capture_output=True, text=True)
        assert p.returncode != 0 and reason in p.stdout + p.stderr, (name, p.stdout[-400:], p.stderr[-400:])
    shutil.rmtree(bad)


def key_margins(eye, body):
    """PQ-376: at `eye`, for a wearer at `body` (heading 0), the least gaps in
    metres between the copies' biased keys and the sparks' keys, the links'
    newest points (n3e's old one key per link) and the copies' biased keys,
    and the sparks' keys and the copies' unbiased keys, over a grid of the
    tail points (the box's 0.25-0.74 of each edge). A spark key may be off by
    its quad's three-corner offset, at most 0.12 x sqrt(2) / 3 < 0.06 m."""
    import itertools
    import math
    lo = [TAIL_BOX[0][k] + .25 * (TAIL_BOX[1 + k][k] - TAIL_BOX[0][k]) for k in range(3)]
    hi = [TAIL_BOX[0][k] + .74 * (TAIL_BOX[1 + k][k] - TAIL_BOX[0][k]) for k in range(3)]
    points = [[body[k] + lo[k] + (hi[k] - lo[k]) * f[k] for k in range(3)]
              for f in itertools.product([i / 4 for i in range(5)], repeat=3)]
    links = [math.dist(q, eye) for q in points]
    sparks = [math.dist([q[k] + SPARK_LIFT * TOWARD[k] for k in range(3)], eye) for q in points]
    origin = [body[k] + SORT["origin"][k] for k in range(3)]
    copies = [math.dist([origin[0], origin[1], origin[2] + j], eye) for j in (-.035, 0, .035)]
    quad = .06
    return (min(copies) + SORT_BIAS - max(sparks) - quad, min(links) - max(copies) - SORT_BIAS,
            min(sparks) - quad - max(copies))


def magenta(r, g, b):
    return r > 150 and b > 150 and g < 90


def clusters(path):
    """Magenta components (4-connected) of at least 40 pixels, and the cyan
    pixel count, in the capture's middle rows (away from the HUD bars)."""
    width, height, pixels = npc_looks_live.read_ppm(path)
    mask, cyan = set(), 0
    for y in range(height // 10, height * 9 // 10):
        row = y * width * 3
        for x in range(width):
            r, g, b = pixels[row + 3 * x:row + 3 * x + 3]
            if magenta(r, g, b):
                mask.add((x, y))
            elif g > 150 and b > 150 and r < 90:
                cyan += 1
    parts = []
    while mask:
        stack, size, top = [mask.pop()], 0, None
        while stack:
            x, y = stack.pop()
            size += 1
            top = y if top is None else min(top, y)
            for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if n in mask:
                    mask.remove(n)
                    stack.append(n)
        if size >= 40:
            parts.append((size, top))
    return sorted(parts, reverse=True), cyan


def live(package):
    from isolation import DISPOSABLE_POSTGRES, container_logs, free_ports
    from readiness import wait_postgres
    from world_peer import Peer, blob, fields, first, integer
    import urllib.request

    manifest = json.loads((package / "recipe.json").read_text())["manifest"]
    out = OUT / "live"
    out.mkdir(parents=True, exist_ok=True)
    server_binary = str(Path(os.environ.get("N3E_TEST_SERVER", "target/debug/n3e-server")).resolve())
    name = "n3e-pq211-" + uuid.uuid4().hex[:10]
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
        p.send(32, integer(1, op) + blob(2, f"pq211-{serial[0]}") + integer(3, first(state, 1)) + integer(4, source)
               + integer(5, destination) + integer(6, first(fields(records[source]), 1)))
        d = wait(p, 33)
        assert first(d, 2) == b"committed", d
        return fields(first(d, 3))

    def keys(p, entity):
        return list(first(p.entities.get(entity, {}), 20, b""))

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

        def peer(account):
            p = Peer(listen, account, passwords[account], content=(package / "release.sha256").read_text().strip(),
                     game=manifest["game_id"], protocol=manifest["protocol_version"])
            p.create(account.title())
            assert p.select(p.characters[0][0])[0] == 10
            return p
        # The first account equips the blade (bag slot 0) in the right hand and
        # leaves: the client's own login then carries committed key 1.
        a = peer("explorer")
        state = bag(a)
        assert first(fields(state[5][0]), 2) == b"demo:item/blade", state[5][0]
        state = bag(a, 5, 0, 0, state)
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
            """Run the test client as the explorer; `steps` run in order, each
            once its line pattern appears in the client's output. The companion
            records where it sees the explorer stand throughout."""
            lines = []
            proc = subprocess.Popen(
                ["build/client/n3e-test-client", str(package), "--connect", f"localhost:{listen}", "--ca",
                 "deploy/local/ca.pem", "--auto-login", "--world-smoke", "14", "--capture", str(capture)],
                env={**os.environ, "N3E_TEST_ACCOUNT": "explorer", "N3E_TEST_PASSWORD": passwords["explorer"],
                     "N3E_TEST_APPEARANCE_EFFECTS": "1", "N3E_TEST_STAND_STILL": "1",
                     "N3E_TEST_EFFECT_PIXELS": CYAN_RANGE,
                     "XDG_CONFIG_HOME": config},
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            reader = threading.Thread(target=lambda: lines.extend(proc.stdout), daemon=True)
            reader.start()
            pending = list(steps)
            stood = set()
            while proc.poll() is None:
                b.pump(.1)
                me = re.search(r"^ENTERED map self=(\d+) ", "".join(lines), re.M)
                if me and int(me.group(1)) in b.entities:
                    e = b.entities[int(me.group(1))]
                    stood.add((round(first(e, 3), 3), round(first(e, 5), 3)))
                if pending and pending[0][0]("".join(lines)):
                    pending.pop(0)[1]()
            reader.join(10)
            text = "".join(lines)
            capture.with_suffix(".log").write_text(text)
            assert proc.returncode == 0 and capture.stat().st_size > 0, (proc.returncode, text[-1500:])
            assert not pending, ("steps not reached", len(pending), text[-1500:])
            # One scene per capture: the explorer stands where it logged in.
            assert len(stood) == 1, ("the explorer moved during the client run", sorted(stood))
            return text
        held = {}

        def unequip():
            held["state"] = bag(b, 6, 0, 0, b_state)
            wait(b, 10, lambda _: keys(b, b.id) == [])

        def equip():
            bag(b, 5, 0, 0, held["state"])
            wait(b, 10, lambda _: keys(b, b.id) == [1])
        other = b.id
        line = r"^APPEARANCE_EFFECT entity={} self={} key=1 copies=3 vertices=12 tails=2 trace={:x} "
        with tempfile.TemporaryDirectory(dir=OUT) as config:
            shown = out / "effects-on.ppm"
            def found(*patterns):
                return lambda text: all(re.search(p, text, re.M) for p in patterns)
            text = client(shown, config, steps=[
                (found(line.format(r"\d+", 1, TRACE), line.format(other, 0, TRACE)), unequip),
                (found(rf"^APPEARANCE_EFFECT_END entity={other} key=1$"), equip)])
            mine = re.findall(line.format(r"(\d+)", 1, TRACE), text, re.M)
            others = re.findall(line.format(other, 0, TRACE), text, re.M)
            ended = re.findall(rf"^APPEARANCE_EFFECT_END entity={other} key=1$", text, re.M)
            # Self once; the other player twice (before the unequip and after
            # the blade came back), ended once in between.
            assert len(mine) == 1 and len(others) == 2 and len(ended) == 1, (mine, others, ended, text[-2000:])
            print("PASS the client draws the effect on itself and on the other player, ends the other's on its "
                  "unequip and starts it again on its re-equip", flush=True)
            # PQ-376: the fixture separates the keys at the client's eye, so
            # only KO's keys show the sparks over the glow; then every frame
            # after the first 30 that drew the effect holds cyan.
            bodies = {}
            for m in re.finditer(r"^APPEARANCE_EFFECT entity=(\d+) .* x=(\S+) y=\S+ z=(\S+) "
                                 r"body_x=(\S+) body_y=(\S+) body_z=(\S+)$", text, re.M):
                x, z, bx, by, bz = (float(v) for v in m.group(2, 3, 4, 5, 6))
                assert abs(x - bx - .55) < 1e-3 and abs(z - bz) < 1e-3, ("heading 0 expected", m.group(0))
                bodies[int(m.group(1))] = (bx, by, bz)
            frames = [(int(f), int(c), tuple(float(v) for v in e.split(",")))
                      for f, c, e in re.findall(r"^EFFECT_PIXELS frame=(\d+) count=(\d+) eye=(\S+)$", text, re.M)]
            measured = frames[30:]
            assert len(bodies) == 2 and len(measured) >= 300, (bodies, len(frames))
            eye = measured[0][2]
            assert all(max(abs(a - b) for a, b in zip(e, eye)) < 1e-3 for _, _, e in measured), "the eye moved"
            margins = {entity: key_margins(eye, body) for entity, body in bodies.items()}
            assert all(min(m) > .1 for m in margins.values()), margins
            empty = [f for f, c, _ in measured if c == 0]
            assert not empty, (f"{len(empty)} of {len(measured)} frames without cyan", empty[:20])
            least = min(c for _, c, _ in measured)
            print(f"PASS every one of {len(measured)} measured frames shows the cyan sparks inside the opaque glow "
                  f"(least {least} px): each spark sorts on its own and each copy at its sort origin plus the "
                  f"bias; key margins at eye {eye}: "
                  + ", ".join(f"{e}: " + "/".join(f"{x:.2f}" for x in m) + " m" for e, m in margins.items()),
                  flush=True)
            Path(config, "n3e").mkdir()
            Path(config, "n3e", "Option.ini").write_text("[WeaponEffect]\nEffectVisible=0\n")
            hidden = out / "effects-off.ppm"
            quiet = client(hidden, config)
            assert "APPEARANCE_EFFECT" not in quiet, quiet[-1500:]
        on, cyan_on = clusters(shown)
        off, cyan_off = clusters(hidden)
        # Two glows (the near one larger and lower on the screen), the tails;
        # none of either with the option off.
        assert len(on) >= 2 and on[0][1] > on[1][1] and cyan_on > 0, (on, cyan_on)
        assert not off and cyan_off == 0, (off, cyan_off)
        print(f"PASS graphical client draws the equipped-item effect on the local and the other player: "
              f"{len(on)} magenta glows {[s for s, _ in on]} px, {cyan_on} cyan tail px; none with "
              f"WeaponEffect.EffectVisible=0; {shown}, {hidden}", flush=True)
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
    assert (package / "effects.bin").read_bytes()[:4] == b"N3E5"
    check_readers(package)
    print("PASS N3E5 package: both readers accept it; the client refuses an effect on a missing key or joint",
          flush=True)
    live(package)
