"""PQ-253: per-template NPC presentation (N3LK + N3NM, engine 38 / wire 30), live.

The package is the PQ-249 engine 37 fixture (tests/npc_templates_live.py) with
two passive, motionless templates standing side by side in front of the player
spawn and a looks table giving each its own synthetic model
(tools/assetc/npc_looks_fixture.py): a red pillar and a blue slab, each with its
own atlas, four clips and clip timing; the slab's entry keeps its name at any
range. A second package carries 52 looks (the per-zone count of the KO homeland
rows), each with a 512 x 512 atlas, to measure the load bounds.

Against a native server on a disposable Postgres and Redis it checks over the
wire that each NPC carries its template's looks key. With N3E_GRAPHICAL=1 the
real test client joins offscreen and must: load both models (NPC_LOOKS_LOAD),
derive each looks' own pick box from its own model (pillar tall and thin, slab
wide and low), draw each NPC with the entry its looks key names (NPC_LOOKS),
pick each through its own box and its own triangles in the looks pick buffer
(NPC_LOOKS_PICK), and show both side by side in the capture (a red region left
of a blue one). It then opens the 52-looks package offscreen (no server) and
reports its load and upload times, which must stay inside the bound below.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tests") not in sys.path:
    sys.path.append(str(ROOT / "tests"))
from isolation import once_per_run  # noqa: E402

OUT = ROOT / "build/pq253"
PLAYER = (-5.0, -5.0)
# In front of the player spawn as the camera first looks, 3 m apart.
SPAWNS = [[-6.5, -9.0], [-3.5, -9.0]]
RED, BLUE = (220, 30, 30), (30, 30, 220)
BASE = dict(acquisition="passive", health=40, level=1, xp=10, damage=1, attack=4, defense=0, accuracy=100,
            evasion=1, attack_ticks=20, speed=0, attack_range=1, search_range=3, tracing_range=8)
TEMPLATES = [dict(name="demo:creature/pillar", looks="demo:looks/pillar", **BASE),
             dict(name="demo:creature/slab", looks="demo:looks/slab", **BASE)]
# The 52-looks package: one template and one spawn per looks.
BOUND_LOOKS, BOUND_ATLAS = 52, 512
# Load bound for the 52-looks package on the reference machine (milliseconds):
# reading and parsing every model and uploading every atlas once at start
# (after the release index has read and hashed each file).
LOAD_BOUND_MS = 3000


@once_per_run
def prepare(looks=2):
    """Cook the engine 38 package with `looks` entries (2: the side-by-side pair;
    BOUND_LOOKS: the load bound); returns its directory."""
    from npc_templates_live import prepare as base
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    import main
    import npc_looks_fixture

    source = base().parent / "source"
    root, out = OUT / f"source-{looks}", OUT / f"package-{looks}"
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(source, root)
    m = json.loads((root / "package.json").read_text())
    if looks == 2:
        templates, points = TEMPLATES, SPAWNS
        entries = [dict(key=t["looks"], name_always=i == 1,
                        clips=npc_looks_fixture.write(root, t["looks"].split("/")[1], shape, color))
                   for i, (t, shape, color) in enumerate(zip(TEMPLATES, ("pillar", "slab"), (RED, BLUE)))]
    else:
        templates = [dict(BASE, name=f"demo:creature/t{i:02}", looks=f"demo:looks/l{i:02}") for i in range(looks)]
        points = [[-20.0 + 4 * (i % 11), 4.0 + 4 * (i // 11)] for i in range(looks)]
        entries = [dict(key=t["looks"], name_always=False,
                        clips=npc_looks_fixture.write(root, f"l{i:02}", ("pillar", "slab")[i % 2],
                                                      (40 + 4 * i, 200 - 3 * i, 60 + i), BOUND_ATLAS))
                   for i, t in enumerate(templates)]
    m["gameplay"].update(spawns=points, spawn_x=PLAYER[0], spawn_z=PLAYER[1])
    m["npc"]["templates"] = templates
    m["npc"]["slots"] = [dict(area=[0, 0, 0, 0], respawn_ticks=60, template=t["name"]) for t in templates]
    m["editing"]["spawns"] = [0, 1]
    m["npc_looks"] = entries
    m.update(engine_version=38, protocol_version=30)
    (root / "package.json").write_text(json.dumps(m))
    main.cook(root, out)
    return out.resolve()


def check_readers(package):
    """Both readers accept the package and bind the same release identity;
    returns the client reader's output."""
    results = []
    for cmd in [["build/client/n3e-asset-check", str(package)], ["target/debug/n3e-server", "--check-content"]]:
        p = subprocess.run(cmd, cwd=ROOT, env={**os.environ, "N3E_PACKAGE": str(package)}, capture_output=True, text=True)
        assert p.returncode == 0, (cmd, p.stdout[-600:], p.stderr[-600:])
        results.append(p.stdout.splitlines())
    assert set(results[0]) & set(results[1]), "readers disagree on the release"
    return results[0]


POSTGRES = "postgres:17.4-bookworm@sha256:304ab813518754228f9f792f79d6da36359b82d8ecf418096c636725f8c930ad"
REDIS = "redis:7.4.2-bookworm@sha256:fbdbaea47b9ae4ecc2082ecdb4e1cea81e32176ffb1dcf643d422ad07427e5d9"


def read_ppm(path):
    data = path.read_bytes()
    fields, at = [], 0
    while len(fields) < 4:
        while data[at:at + 1].isspace():
            at += 1
        end = at
        while not data[end:end + 1].isspace():
            end += 1
        fields.append(data[at:end])
        at = end
    width, height = int(fields[1]), int(fields[2])
    return width, height, data[at + 1:at + 1 + width * height * 3]


def regions(path):
    """Pixel count and mean column of the strongly red and strongly blue pixels
    in the capture's middle (away from the HUD bars)."""
    width, height, pixels = read_ppm(path)
    found = {"red": [0, 0], "blue": [0, 0]}
    for y in range(height // 5, height * 4 // 5):
        row = y * width * 3
        for x in range(width // 5, width * 4 // 5):
            r, g, b = pixels[row + 3 * x:row + 3 * x + 3]
            if r > 60 and r > 2 * g and r > 2 * b:
                found["red"][0] += 1
                found["red"][1] += x
            elif b > 60 and b > 2 * r and b > 2 * g:
                found["blue"][0] += 1
                found["blue"][1] += x
    return {k: (n, total / n if n else None) for k, (n, total) in found.items()}


def bound_load(package):
    """The 52-looks package in the offscreen client without a server: its
    NPC_LOOKS_LOAD line (load and upload times)."""
    log = OUT / "bound-client.log"
    with open(log, "w") as out:
        code = subprocess.run(["build/client/n3e-test-client", str(package), "--smoke"], cwd=ROOT,
                              stdout=out, stderr=subprocess.STDOUT, timeout=120).returncode
    text = log.read_text()
    line = re.search(r"^NPC_LOOKS_LOAD looks=(\d+) texture_bytes=(\d+) load_ms=(\d+) upload_ms=(\d+)$", text, re.M)
    assert code == 0 and line, (code, text[-1500:])
    looks, texels, load, upload = map(int, line.groups())
    assert looks == BOUND_LOOKS and texels == BOUND_LOOKS * BOUND_ATLAS * BOUND_ATLAS * 3, line.group(0)
    assert load + upload <= LOAD_BOUND_MS, line.group(0)
    return looks, texels, load, upload


def live(package):
    from isolation import DISPOSABLE_POSTGRES, container_logs, free_ports
    from readiness import wait_postgres
    from world_peer import Peer, first
    import urllib.request

    manifest = json.loads((package / "recipe.json").read_text())["manifest"]
    out = OUT / "live"
    out.mkdir(parents=True, exist_ok=True)
    server_binary = str(Path(os.environ.get("N3E_TEST_SERVER", "target/debug/n3e-server")).resolve())
    name = "n3e-pq253-" + uuid.uuid4().hex[:10]
    password = "test-only-" + uuid.uuid4().hex
    containers, server, log = [], None, None

    def run(*cmd, env=None, stdin=None):
        p = subprocess.run(cmd, env=env, input=stdin, capture_output=True, text=True, timeout=120)
        assert p.returncode == 0, (cmd, p.returncode, p.stdout, p.stderr)
        return p.stdout

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
        env = dict(os.environ, DATABASE_URL=f"host=127.0.0.1 port={pg} user=n3e password=test-only dbname=n3e",
                   REDIS_ADDRESS=redis, N3E_PACKAGE=str(package), N3E_REALM="test-" + name,
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
        p.pump(1.0)
        npcs = {first(e, 2).decode(): e for e in p.entities.values() if first(e, 9) == 1}
        assert set(npcs) == {t["name"] for t in TEMPLATES}, npcs.keys()
        for t in TEMPLATES:
            e = npcs[t["name"]]
            assert first(e, 31, b"").decode() == t["looks"], (t["name"], e)
        ids = {t["looks"]: first(npcs[t["name"]], 1) for t in TEMPLATES}
        print("PASS both templates in one view carry their own looks key on the wire", flush=True)
        p.logout()
        if os.environ.get("N3E_GRAPHICAL") == "1":
            capture = out / "looks.ppm"
            capture.unlink(missing_ok=True)
            with open(out / "client.log", "w") as client_log:
                code = subprocess.run(
                    ["build/client/n3e-test-client", str(package), "--connect", f"localhost:{listen}", "--ca",
                     "deploy/local/ca.pem", "--auto-login", "--world-smoke", "6", "--capture", str(capture)],
                    env={**os.environ, "N3E_TEST_ACCOUNT": "explorer", "N3E_TEST_PASSWORD": password,
                         "N3E_TEST_NPC_LOOKS": "1"},
                    stdout=client_log, stderr=subprocess.STDOUT, timeout=120).returncode
            text = (out / "client.log").read_text()
            assert code == 0 and capture.stat().st_size > 0, (code, text[-1500:])
            load = re.search(r"^NPC_LOOKS_LOAD looks=2 texture_bytes=96 ", text, re.M)
            assert load, text[-1500:]
            boxes = {m.group(1): tuple(map(float, m.group(2).split(","))) + (int(m.group(3)),)
                     for m in re.finditer(r"^NPC_LOOKS_BOX looks=\d+ key=(\S+) size=(\S+) dead_height=\S+ "
                                          r"name_always=(\d)$", text, re.M)}
            pillar, slab = boxes["demo:looks/pillar"], boxes["demo:looks/slab"]
            # Each looks' own box: the pillar taller than wide, the slab wider than tall.
            assert pillar[1] > 1.5 and pillar[0] < 0.8 and slab[0] > 1.3 and slab[1] < 1.0, boxes
            assert (pillar[3], slab[3]) == (0, 1), boxes
            drawn = {int(m.group(1)): (m.group(2), int(m.group(3)), int(m.group(4)))
                     for m in re.finditer(r"^NPC_LOOKS entity=(\d+) key=(\S+) looks=(\d+) fallback=(\d)$", text, re.M)}
            for index, t in enumerate(TEMPLATES):
                assert drawn.get(ids[t["looks"]]) == (t["looks"], index, 0), (t["looks"], drawn)
            picks = {int(m.group(1)): (int(m.group(2)), int(m.group(3)))
                     for m in re.finditer(r"^NPC_LOOKS_PICK entity=(\d+) picked=(\d+) mesh=(\d) vertices=\d+$",
                                          text, re.M)}
            for entity in ids.values():
                assert picks.get(entity) == (entity, 1), (entity, picks)
            found = regions(capture)
            (red, red_x), (blue, blue_x) = found["red"], found["blue"]
            assert red > 200 and blue > 200 and red_x < blue_x, found
            print(f"PASS graphical client draws two templates side by side with their own models: pillar {red} red px "
                  f"at x {red_x:.0f}, slab {blue} blue px at x {blue_x:.0f}; own boxes {boxes}; picks {picks}; "
                  f"{capture}", flush=True)
            looks, texels, ms_load, ms_upload = bound_load(prepare(BOUND_LOOKS))
            print(f"PASS {looks} looks load offscreen: {texels} atlas bytes, read {ms_load} ms, upload {ms_upload} ms "
                  f"(bound {LOAD_BOUND_MS} ms)", flush=True)
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
    lines = check_readers(package)
    assert any(line.startswith("npc looks 2 texture_bytes 96 ") for line in lines), lines
    print("PASS N3LK engine 38 package: both readers accept two looks", flush=True)
    bound = prepare(BOUND_LOOKS)
    lines = check_readers(bound)
    print("PASS both readers accept the 52-looks package:",
          next(line for line in lines if line.startswith("npc looks ")), flush=True)
    live(package)
