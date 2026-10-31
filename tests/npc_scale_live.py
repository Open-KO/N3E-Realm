"""PQ-272: per-template NPC drawn scale (N3N4, engine 41 / wire 30), live.

KO's servers carry each template's sSize to the client: the AI spawn load copies
template +0x28 to record +0x24 (AI 00438c42), its NPC info record sends it as the
fourth short (004221d5), Ebenezer stores it at NPC +0x22 (00408f7d, 00407987) and
writes it into every NPC-in record after the looks key, the type byte and a u32
(00479e7c). The client's NPC-in multiplies it by 0.01 (005cdd82) and gives it to
the character (0041f800), whose matrix carries it on its diagonal (0043b650); the
render passes that matrix to device slot +0x94 with 256 (004197e0: the world
transform by inference, SetTransform / D3DTS_WORLD) and the pick tests the box
with it; the name callback multiplies the label height by it (00459820).
evidence/pq-272-ko-npc-drawn-scale.md labels each claim.

The package is the PQ-253 fixture (tests/npc_looks_live.py) with two passive,
motionless templates standing side by side in front of the player spawn that
share one looks model, the red pillar: the left template has no scale (100 %),
the right one 200 %, as two KO templates may share an sPid and differ in sSize.

Against a native server on a disposable Postgres and Redis it checks over the
wire that the scaled NPC carries Entity.scale 200 and the other none. With
N3E_GRAPHICAL=1 the real test client joins offscreen and must report each NPC's
scale with the height of the pick box it placed (NPC_SCALE) and the height its
label is drawn at, printed where the label is projected (NPC_LABEL), both twice
as high at 200 % (the fixture has no nameplate style, so the label is the demo
HUD's; the styled anchor's scaling is checked by build/client/n3e-nameplate-check
on name_anchor, which the styled draw calls), pick each through its own box and
triangles (NPC_LOOKS_PICK), and draw the right pillar about twice as tall and wide
as the left in the capture. PQ-375: the capture is taken with the player standing
still (N3E_TEST_STAND_STILL) and the pillars' idle clip unturned, so the camera and
both silhouettes are the same each run; the world smoke's walk and the idle turn
had made the width ratio follow the phases the capture landed on (2.30 to 2.56).

PQ-296: the package also carries an original synthetic target marker. The client
selects each picked NPC in turn and reports the marker it drew (TARGET_MARKER):
KO's target symbol scales by the selected actor's radius and height times its
scale +0x90 (client 005c4e20 -> 0045a1d0, 00459ff0), so the upright part spans
2 x radius x scale across and 1.3 x height x scale high, twice as large at
200 %. The selection is cleared before the capture.
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
import npc_looks_live  # noqa: E402

OUT = ROOT / "build/pq272"
BASE = npc_looks_live.BASE
LOOKS = "demo:looks/pillar"
TEMPLATES = [dict(name="demo:creature/pillar", looks=LOOKS, **BASE),
             dict(name="demo:creature/giant", looks=LOOKS, scale=200, **BASE)]
# Farther than the PQ-253 pair so the 3.6 m pillar stays inside the frame.
SPAWNS = [[-6.5, -12.0], [-3.5, -12.0]]


@once_per_run
def prepare():
    """Cook the engine 41 package (N3N4 templates sharing one looks); returns its directory."""
    from npc_templates_live import prepare as base
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    import main
    import npc_looks_fixture

    source = base().parent / "source"
    root, out = OUT / "source", OUT / "package"
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(source, root)
    m = json.loads((root / "package.json").read_text())
    # PQ-375: the idle clip holds the pillars unturned, so their silhouettes
    # do not follow the idle phase the capture lands on.
    clips = npc_looks_fixture.write(root, "pillar", "pillar", npc_looks_live.RED, still=True)
    m["gameplay"].update(spawns=SPAWNS, spawn_x=npc_looks_live.PLAYER[0], spawn_z=npc_looks_live.PLAYER[1])
    m["npc"]["templates"] = TEMPLATES
    m["npc"]["slots"] = [dict(area=[0, 0, 0, 0], respawn_ticks=60, template=t["name"]) for t in TEMPLATES]
    m["editing"]["spawns"] = [0, 1]
    m["npc_looks"] = [dict(key=LOOKS, name_always=False, clips=clips)]
    m.update(engine_version=41, protocol_version=30)
    # PQ-296: an original synthetic target marker (one upright unit quad), so
    # the client's marker is drawn at each selected NPC's scale.
    (root / "target-marker.bin").write_bytes(marker())
    m["presentation"]["target-marker.bin"] = "target-marker.bin"
    (root / "package.json").write_text(json.dumps(m))
    main.cook(root, out)
    return out.resolve()


# N3TM: diameter and height multipliers, ground lift, then (radius, height) for
# the player and for an NPC (content/target-marker.md).
MARKER = dict(diameter=2.0, height=1.3, lift=0.1, player=(0.5, 1.8), npc=(0.4, 1.0))


def marker():
    """One upright, camera-facing unit quad (mode 1), 1 x 1 green texel. The
    fixture's world has no terrain parts, the ground a mode 0 part samples
    (content/target-marker.md), so a ground part would draw nothing here;
    build/client/n3e-target-marker-check scales the ground part."""
    import struct

    def f(*v):
        return struct.pack("<%df" % len(v), *v)

    def u(*v):
        return struct.pack("<%dI" % len(v), *v)

    data = b"N3TM" + f(MARKER["diameter"], MARKER["height"], MARKER["lift"], *MARKER["player"], *MARKER["npc"]) + u(1)
    for mode, pivot, corners, normal in [
            (1, (0, 1, 0), [(-.5, 0, 0), (.5, 0, 0), (.5, 1, 0), (-.5, 1, 0)], (0, 0, 1))]:
        data += u(mode) + f(*pivot) + u(1, 1) + bytes([0, 255, 0, 255]) + u(4)
        for k, c in enumerate(corners):
            data += f(*c, *normal, k % 2, k // 2)
        data += u(6, 0, 1, 2, 0, 2, 3)
    return data


def extents(path):
    """Bounding box (x0, y0, x1, y1) and pixel count of the strongly red pixels
    left and right of the capture's centre column, between 35 % and 80 % of its
    width (clear of the HUD's red health bar and the side buttons)."""
    width, height, pixels = npc_looks_live.read_ppm(path)
    found = {"left": [width, height, -1, -1, 0], "right": [width, height, -1, -1, 0]}
    for y in range(height):
        row = y * width * 3
        for x in range(width * 35 // 100, width * 4 // 5):
            r, g, b = pixels[row + 3 * x:row + 3 * x + 3]
            if r > 60 and r > 2 * g and r > 2 * b:
                box = found["left" if x < width // 2 else "right"]
                box[0], box[1], box[2], box[3] = min(box[0], x), min(box[1], y), max(box[2], x), max(box[3], y)
                box[4] += 1
    return found


def live(package):
    from isolation import DISPOSABLE_POSTGRES, container_logs, free_ports
    from readiness import wait_postgres
    from world_peer import Peer, first
    import urllib.request

    manifest = json.loads((package / "recipe.json").read_text())["manifest"]
    out = OUT / "live"
    out.mkdir(parents=True, exist_ok=True)
    server_binary = str(Path(os.environ.get("N3E_TEST_SERVER", "target/debug/n3e-server")).resolve())
    name = "n3e-pq272-" + uuid.uuid4().hex[:10]
    password = "test-only-" + uuid.uuid4().hex
    containers, server, log = [], None, None

    def run(*cmd, env=None, stdin=None):
        p = subprocess.run(cmd, env=env, input=stdin, capture_output=True, text=True, timeout=120)
        assert p.returncode == 0, (cmd, p.returncode, p.stdout, p.stderr)
        return p.stdout

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
        scales = {t["name"]: first(npcs[t["name"]], 33, 0) for t in TEMPLATES}
        assert all(first(npcs[t["name"]], 31, b"").decode() == LOOKS for t in TEMPLATES), npcs
        # 100 % is sent as nothing (older golden bytes unchanged); 200 % as 200.
        assert scales == {"demo:creature/pillar": 0, "demo:creature/giant": 200}, scales
        # The player entity carries no scale.
        assert all(first(e, 33, 0) == 0 for e in p.entities.values() if first(e, 9) != 1)
        ids = {t["name"]: first(npcs[t["name"]], 1) for t in TEMPLATES}
        print(f"PASS the two templates share one looks key and carry their own scale on the wire: {scales}",
              flush=True)
        p.logout()
        if os.environ.get("N3E_GRAPHICAL") == "1":
            capture = out / "scale.ppm"
            capture.unlink(missing_ok=True)
            with open(out / "client.log", "w") as client_log:
                code = subprocess.run(
                    ["build/client/n3e-test-client", str(package), "--connect", f"localhost:{listen}", "--ca",
                     "deploy/local/ca.pem", "--auto-login", "--world-smoke", "6", "--capture", str(capture)],
                    # PQ-375: the world smoke's player stands still, so the
                    # camera, and with it each pillar's perspective, is the
                    # same at every capture (its walk's phase follows the
                    # login's wall time).
                    env={**os.environ, "N3E_TEST_ACCOUNT": "explorer", "N3E_TEST_PASSWORD": password,
                         "N3E_TEST_NPC_LOOKS": "1", "N3E_TEST_STAND_STILL": "1"},
                    stdout=client_log, stderr=subprocess.STDOUT, timeout=120).returncode
            text = (out / "client.log").read_text()
            assert code == 0 and capture.stat().st_size > 0, (code, text[-1500:])
            labels = {int(m.group(1)): float(m.group(2))
                      for m in re.finditer(r"^NPC_LABEL entity=(\d+) height=(\S+) style=0$", text, re.M)}
            reported = {int(m.group(1)): tuple(map(float, m.group(2, 3))) + (labels.get(int(m.group(1)), -1.0),)
                        for m in re.finditer(r"^NPC_SCALE entity=(\d+) scale=(\S+) box_height=(\S+)$", text, re.M)}
            small, big = reported.get(ids["demo:creature/pillar"]), reported.get(ids["demo:creature/giant"])
            assert small and big, (reported, ids)
            # Scale 1 and 2; the placed box twice as high.
            assert (small[0], big[0]) == (1.0, 2.0), reported
            assert small[1] > 1.5 and abs(big[1] - 2 * small[1]) < 1e-3, reported
            # The name label as drawn (NPC_LABEL, printed where the label is
            # projected): this fixture has no nameplate style, so the demo HUD's
            # fixed NPC label height (0.65 m) times the scale. The styled
            # anchor's scaling is build/client/n3e-nameplate-check's
            # (name_anchor, the function the styled draw calls).
            assert abs(small[2] - 0.65) < 1e-5 and abs(big[2] - 1.3) < 1e-5, reported
            picks = {int(m.group(1)): (int(m.group(2)), int(m.group(3)))
                     for m in re.finditer(r"^NPC_LOOKS_PICK entity=(\d+) picked=(\d+) mesh=(\d) vertices=\d+$",
                                          text, re.M)}
            for entity in ids.values():
                assert picks.get(entity) == (entity, 1), (entity, picks)
            # PQ-296: each NPC selected in turn; the marker drawn at its scale.
            # The upright unit quad, turned to the camera about y, spans
            # 2 x radius x scale across (the hypotenuse of its x and z extents)
            # and 1.3 x height x scale on y.
            drawn = {}
            for m in re.finditer(r"^TARGET_MARKER entity=(\d+) npc=(\d) scale=(\S+) horizontal=(\S+) vertical=(\S+) "
                                 r"part=(\d) mode=(\d) x=(\S+) y=(\S+) z=(\S+)$", text, re.M):
                drawn.setdefault(int(m.group(1)), {})[int(m.group(6))] = (
                    int(m.group(2)), float(m.group(3)), float(m.group(4)), float(m.group(5)), int(m.group(7)),
                    float(m.group(8)), float(m.group(9)), float(m.group(10)))
            marked = {}
            for entity, scale in ((ids["demo:creature/pillar"], 1.0), (ids["demo:creature/giant"], 2.0)):
                parts = drawn.get(entity, {})
                assert set(parts) == {0}, ("marker not drawn", entity, drawn)
                upright = parts[0]
                horizontal = MARKER["diameter"] * MARKER["npc"][0] * scale
                vertical = MARKER["height"] * MARKER["npc"][1] * scale
                across = (upright[5] ** 2 + upright[7] ** 2) ** .5
                assert upright[:2] == (1, scale) and upright[4] == 1, (entity, parts)
                assert abs(upright[2] - horizontal) < 1e-4 and abs(upright[3] - vertical) < 1e-4, (entity, parts)
                assert abs(across - horizontal) < 1e-3 and abs(upright[6] - vertical) < 1e-3, (entity, parts)
                marked[entity] = (across, upright[6])
            small_marker, big_marker = marked[ids["demo:creature/pillar"]], marked[ids["demo:creature/giant"]]
            print(f"PASS target marker drawn at each NPC's scale: {small_marker[0]:.3f} m across and "
                  f"{small_marker[1]:.3f} m high at 100 %, {big_marker[0]:.3f} m and {big_marker[1]:.3f} m at 200 % "
                  f"(NPC profile {MARKER['npc']}, x {MARKER['diameter']} / x {MARKER['height']})", flush=True)
            found = extents(capture)
            left, right = found["left"], found["right"]
            assert left[4] > 100 and right[4] > 100, found
            tall = (right[3] - right[1] + 1) / (left[3] - left[1] + 1)
            wide = (right[2] - right[0] + 1) / (left[2] - left[0] + 1)
            area = right[4] / left[4]
            # Perspective keeps the ratios near, not at, 2 (and 4 for the
            # area). PQ-375: with the player and the pillars still, the capture
            # is the same each run (height x2.09, width x2.00, area x4.11 on
            # 29 and 58 px wide silhouettes, evidence/pq-375-npc-scale-live-width-ratio-flake.md); the bounds
            # leave about 2 px of the small silhouette for another rasteriser.
            assert 1.95 < tall < 2.25 and 1.85 < wide < 2.15 and 3.7 < area < 4.6, (tall, wide, area, found)
            print(f"PASS graphical client draws one looks model at each template's scale: {left[4]} red px "
                  f"left, {right[4]} right; height x{tall:.2f}, width x{wide:.2f}, area x{area:.2f}; placed box "
                  f"heights {small[1]:.3f}/{big[1]:.3f} m, label heights {small[2]:.3f}/{big[2]:.3f} m; "
                  f"picks {picks}; {capture}", flush=True)
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
    assert (package / "npc.bin").read_bytes()[:8] == b"N3N4\x04\0\0\0"
    lines = npc_looks_live.check_readers(package)
    assert any(line.startswith("npc looks 1 texture_bytes 48 ") for line in lines), lines
    print("PASS N3N4 engine 41 package: both readers accept two scaled templates sharing one looks", flush=True)
    live(package)
