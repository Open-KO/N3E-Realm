"""PQ-217: the zone overview map on the basic HUD (N3HE), against a live server.

Original synthetic data only. The demo package gets a minimal N3HE HUD
written here in the format tools/assetc/ko_hud.py cooks (tests/hud_import.py
checks the cooker's own output against the readers in make test; this suite
does not import the KO HUD cooker, so its modules stay out of the live tier):
a 256 px overview image on panel 15 and the map button's click region.
The overview map covers a 100 m square whose corner is 7 m from the origin, so
the map window (a sixth of the map at zoom 6) is clamped at that corner: the
heading arrow sits off the image centre at the player's position, and the
demo's two NPCs appear as markers at theirs, which the client draws only when it
rebuilds the markers from the world each frame.

Always: the cooked HUD is N3HE, the client's asset check and the server's
content check accept the package. With N3E_GRAPHICAL=1 (make live) one test
client logs in on a disposable Compose stack and runs the minimap replay
(N3E_TEST_PANELS=minimap): hidden at start, M opens it with the arrow at the
player's map position, the map button closes it.
"""
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path("tools/assetc").resolve()))
from isolation import DISPOSABLE_COMPOSE, container_logs  # noqa: E402
from world_peer import Peer  # noqa: E402

B = Path("build/overview-map-live")
shutil.rmtree(B, ignore_errors=True)
B.mkdir(parents=True)
MAP = (8, 40, 264, 296)  # the image, in pixels from the top-left (pixel scale policy 1)
EXTENT = 100.0
ORIGIN = (-7.0, -7.0)
COLOURS = (0xff00ff00, 0xff800000, 0xff00a0ff, 0xffffff00, 0xff0040ff)  # as ko_hud: self, NPC, ...


def u(n):
    return struct.pack("<I", n)


def f(*xs):
    return struct.pack("<%df" % len(xs), *xs)


def string(text):
    return u(len(text)) + text.encode("ascii")


def record(kind, anchor, rect, texture, binding, panel):
    """One N3HE record: N3HB's fields, then the panel word (ko_hud.cook)."""
    return (u(kind) + f(*anchor) + f(*rect) + u(texture) + f(0, 0, 1, 1) + string(binding) + string("")
            + u(0xffffffff) + u(0) + u(0) + u(0) + u(15) + u(0) + u(panel))


def hud(npc_health, level_xp):
    font = (256, 128, bytes(256 * 128 * 4))
    # A blue-grey checker, so neither marker colour occurs in the map itself.
    overview = (64, 64, b"".join(bytes((40, 60 + 40 * ((x // 8 + y // 8) % 2), 160, 255))
                                 for y in range(64) for x in range(64)))
    textures = [font, overview]
    data = b"N3HE" + u(1) + u(0) + f(npc_health, level_xp) + u(len(textures))
    data += b"".join(u(w) + u(h) + pixels for w, h, pixels in textures)
    data += f(7) + u(14) + u(5) + u(0)  # font metrics; no controls
    records = [record(0, (0, 0), MAP, 1, "minimap", 15),
               record(2, (0.5, 1), (-24, -24, 24, 0), 0, "toggle_minimap", 0)]
    data += u(len(records)) + b"".join(records)
    # The overview block: texture, origin, extent, zoom 6, arrow height/30, 2/1 px markers, colours.
    return data + u(1) + f(*ORIGIN) + f(EXTENT, 6, 1 / 30, 2, 1) + b"".join(u(c) for c in COLOURS)


source, package = B / "source", B / "package"
shutil.copytree("games/demo", source)
manifest = json.loads((source / "package.json").read_text())
(source / "hud.bin").write_bytes(hud(manifest["gameplay"]["npc_health"], manifest["gameplay"]["level_xp"]))
import main  # noqa: E402
content = main.cook(source, package)
assert (package / "hud.bin").read_bytes()[:4] == b"N3HE"
check = subprocess.run(["build/client/n3e-asset-check", str(package)], capture_output=True, text=True)
assert check.returncode == 0, check.stdout[-2000:] + check.stderr[-2000:]
server = subprocess.run(["target/debug/n3e-server", "--check-content"], capture_output=True, text=True,
                        env={**os.environ, "N3E_PACKAGE": str(package)})
assert server.returncode == 0, server.stdout[-2000:] + server.stderr[-2000:]
print("PASS N3HE package: the demo with an overview map on the basic HUD cooks, and the client's asset "
      "check and the server's content check accept it", flush=True)

if os.environ.get("N3E_GRAPHICAL") != "1":
    print("UNVERIFIED: N3HE overview map graphical replay; rerun with N3E_GRAPHICAL=1", flush=True)
    sys.exit(0)

project = "n3e-overview-" + uuid.uuid4().hex[:10]
realm = "test-" + project  # convert-progression accepts only a test- realm
env = {**os.environ, "N3E_PORT": "0", "N3E_REALM": realm, "N3E_PACKAGE_PATH": str(package.resolve()),
       "N3E_UID": str(os.getuid()), "N3E_GID": str(os.getgid())}
base = ["docker", "compose", *DISPOSABLE_COMPOSE, "-p", project]
password = "test-only-" + uuid.uuid4().hex


def dc(*args, stdin=None):
    p = subprocess.run(base + list(args), env=env, input=stdin, text=True, capture_output=True, timeout=120)
    assert p.returncode == 0, (args, p.stdout, p.stderr)
    return p.stdout


def ppm(path):
    data = Path(path).read_bytes()
    parts = data.split(maxsplit=4)
    assert parts[0] == b"P6"
    return int(parts[1]), int(parts[2]), parts[4]


def region(path, rect):
    width, _, pixels = ppm(path)
    out = {}
    for y in range(rect[1], rect[3]):
        for x in range(rect[0], rect[2]):
            i = (y * width + x) * 3
            out[x, y] = tuple(pixels[i:i + 3])
    return out


try:
    # The demo's reward policy is converted once per realm before the server
    # admits it (as tools/play-moradon-preview does).
    dc("up", "-d", "--wait", "postgres", "redis")
    dc("run", "--rm", "--no-deps", "migrate")
    dc("run", "--rm", "--no-deps", "-e", "N3E_TEST_PROGRESSION=disposable", "server", "convert-progression")
    dc("up", "-d", "--wait", "server")
    port = int(dc("port", "server", "7777").strip().rsplit(":", 1)[1])
    dc("exec", "-T", "server", "n3e-server", "account-create", "overview", stdin=password + "\n")
    peer = Peer(port, "overview", password, content=content, game=manifest["game_id"],
                protocol=manifest["protocol_version"])
    peer.create("Mapper")
    peer.s.close()
    shots = B / "minimap"
    log = B / "client.log"
    with log.open("w") as out:
        code = subprocess.run(["build/client/n3e-test-client", str(package), "--connect", f"localhost:{port}",
                               "--ca", "deploy/local/ca.pem", "--auto-login", "--fixed-window", "1024x768",
                               "--world-smoke", "90", "--capture", str(shots)],
                              env={**os.environ, "N3E_TEST_ACCOUNT": "overview", "N3E_TEST_PASSWORD": password,
                                   "N3E_TEST_PANELS": "minimap"},
                              stdout=out, stderr=subprocess.STDOUT, timeout=150).returncode
    text = log.read_text(errors="replace")
    assert code == 0, text[-2000:]
    states = {m[0]: (m[1], [int(float(v)) for v in m[2].split(",")], float(m[3]), float(m[4]))
              for m in re.findall(r"MINIMAP (open|closed) open=([01]) rect=(\S+) self=\S+ player=(\S+),(\S+)", text)}
    assert states["open"][0] == "1" and states["closed"][0] == "0", states
    rect, player = states["open"][1], states["open"][2:]
    assert rect == list(MAP), rect  # pixel scale policy 1: authored pixels, top-left anchored
    opened, closed = region(str(shots) + ".open.ppm", rect), region(str(shots) + ".closed.ppm", rect)
    changed = sum(1 for k in opened if opened[k] != closed[k])
    assert changed > len(opened) // 2, (changed, len(opened))
    width, height = rect[2] - rect[0], rect[3] - rect[1]

    def drawn_at(x, z):
        """presentation.h map_point: the window, half a sixth wide, follows the
        player and is clamped to the map."""
        u, v = (x - ORIGIN[0]) / EXTENT, (z - ORIGIN[1]) / EXTENT
        cu = min(max((player[0] - ORIGIN[0]) / EXTENT, 1 / 12), 11 / 12)
        cv = min(max((player[1] - ORIGIN[1]) / EXTENT, 1 / 12), 11 / 12)
        return rect[0] + (0.5 + (u - cu) * 6) * width, rect[1] + (0.5 + (v - cv) * 6) * height

    def near(points, at, reach):
        return [p for p in points if abs(p[0] - at[0]) <= reach and abs(p[1] - at[1]) <= reach]

    # The heading arrow (colour 0, green) at the player's map point.
    green = [k for k, c in opened.items() if c == (0, 255, 0)]
    assert not any(c == (0, 255, 0) for c in closed.values()), "arrow drawn while closed"
    arrow = drawn_at(*player)
    assert len(green) >= 10 and len(near(green, arrow, 14)) == len(green), (arrow, green[:5], len(green))
    # Each NPC (colour 1) as a marker at its spawn point; none while closed.
    red = [k for k, c in opened.items() if c == (128, 0, 0)]
    assert not any(c == (128, 0, 0) for c in closed.values()), "markers drawn while closed"
    spawns = manifest["gameplay"]["spawns"]
    for x, z in spawns:
        assert near(red, drawn_at(x, z), 6), ((x, z), drawn_at(x, z), red)
    print("PASS N3HE overview map graphical: hidden at start, M opens the %dx%d map with the heading arrow "
          "at the player's clamped map point (%.0f, %.0f) and %d NPC markers at their spawns, the map "
          "button closes it" % (width, height, *arrow, len(spawns)), flush=True)
finally:
    container_logs("compose", [*base, "logs", "--no-color", "--timestamps"], env=env)
    subprocess.run(base + ["down", "-v", "--remove-orphans"], env=env, capture_output=True, timeout=120)
