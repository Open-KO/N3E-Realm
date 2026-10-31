"""PQ-265: NPC looks models with render states (N3MM, engine 39 / wire 30), live.

KO's part renderer 00412570 draws each character part with its material's
render flags (alpha blending with the material's factors, culling off,
lighting off, fog off), in part order, with the alpha test on for every part
(0043ade0: GREATER against reference 0), so a texel of alpha 0 is never drawn
(evidence/pq-265-ko-character-part-materials.md labels each claim). n3e
carries the blend, culling off, lighting off and the alpha test (the fog-off
flag is refused by the converter) as N3SM clips and N3MM models whose render
runs the client draws in order, each with its state.

The package is the PQ-253 fixture (tests/npc_looks_live.py) with two passive,
motionless templates standing side by side in front of the player spawn, each
with a two-part synthetic model (tools/assetc/npc_looks_fixture.py):

* glass (left): an opaque red box inside a larger blue box drawn second with
  source-alpha blending at alpha 128, so the red box shows through the blue
  as purple (without the blend the blue covers it; drawn in the other order
  the blue's depth hides it), and above them a cyan roof facing down, unlit
  and double-sided: the camera looks down on it, so it is a back face that
  only a double-sided run draws.
* cutout (right): an opaque green box inside a larger, closed yellow box,
  unlit (its pixels are the texture's own yellow), whose texture is alpha 0 on
  the left of each face, so the alpha test opens a hole through which the
  green box shows (without the test the yellow box hides it).

Against a native server on a disposable Postgres and Redis it checks over
the wire that each NPC carries its looks key. With N3E_GRAPHICAL=1 the real
test client joins offscreen and must load both models with their runs
(NPC_LOOKS_RUNS) and show, in the capture, purple left of green, cyan, and
yellow and cyan pixels at their textures' colours.
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

OUT = ROOT / "build/pq265"
BASE = npc_looks_live.BASE
TEMPLATES = [dict(name="demo:creature/glass", looks="demo:looks/glass", **BASE),
             dict(name="demo:creature/cutout", looks="demo:looks/cutout", **BASE)]
YELLOW, CYAN = (230, 200, 30), (30, 220, 220)
# Three 8 x 8 regions: the inner box (x 0-7), the outer box (x 8-15) and the roof (x 16-23).
ATLAS = (24, 8)


def atlas(inner, outer, roof=(0, 0, 0, 255)):
    """RGBA texels: `inner` on x 0-7, `outer(x)` (an RGBA tuple) on x 8-15, `roof` on x 16-23."""
    width, height = ATLAS
    return b"".join(bytes(inner if x < 8 else outer(x) if x < 16 else roof)
                    for _ in range(height) for x in range(width))


def models(fixture):
    """{looks key: (parts, rgba)} of the two synthetic models."""
    inner_uv, outer_uv, roof_uv = (0.5 / 24, 7.5 / 24), (8.5 / 24, 15.5 / 24), (16.5 / 24, 23.5 / 24)
    opaque = (0, 0.0, 0, 0)
    return {
        "demo:looks/glass": (
            [fixture.shell((0.5, 1.2, 0.5), *inner_uv) + opaque,
             fixture.shell((0.9, 1.6, 0.9), *outer_uv)
             + (fixture.BLEND, 0.0, fixture.SRC_ALPHA, fixture.ONE_MINUS_SRC_ALPHA),
             fixture.roof((0.6, 0, 0.6), 2.2, *roof_uv) + (fixture.DOUBLE_SIDED | fixture.UNLIT, 0.0, 0, 0)],
            atlas((220, 30, 30, 255), lambda x: (30, 30, 220, 128), CYAN + (255,))),
        "demo:looks/cutout": (
            [fixture.shell((0.5, 1.2, 0.5), *inner_uv) + opaque,
             fixture.shell((0.9, 1.6, 0.9), *outer_uv) + (fixture.UNLIT, 0.0, 0, 0)],
            atlas((30, 200, 30, 255), lambda x: YELLOW + ((0,) if x < 12 else (255,)))),
    }


@once_per_run
def prepare():
    """Cook the engine 39 package with the two material looks; returns its directory."""
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
    entries = []
    for t in TEMPLATES:
        parts, rgba = models(npc_looks_fixture)[t["looks"]]
        clips = npc_looks_fixture.write_materials(root, t["looks"].split("/")[1], parts, *ATLAS, rgba)
        entries.append(dict(key=t["looks"], name_always=False, clips=clips))
    m["gameplay"].update(spawns=npc_looks_live.SPAWNS, spawn_x=npc_looks_live.PLAYER[0],
                         spawn_z=npc_looks_live.PLAYER[1])
    m["npc"]["templates"] = TEMPLATES
    m["npc"]["slots"] = [dict(area=[0, 0, 0, 0], respawn_ticks=60, template=t["name"]) for t in TEMPLATES]
    m["editing"]["spawns"] = [0, 1]
    m["npc_looks"] = entries
    m.update(engine_version=39, protocol_version=30)
    (root / "package.json").write_text(json.dumps(m))
    main.cook(root, out)
    return out.resolve()


def classify(path):
    """Pixel counts (and mean column) in the capture's middle: purple (red seen
    through blue glass), green (the inner box through the cutout's hole),
    yellow and cyan, with how many of the yellow and cyan are within 8 of
    their texture's colour."""
    width, height, pixels = npc_looks_live.read_ppm(path)
    found = {k: [0, 0] for k in ("purple", "green", "yellow", "cyan", "exact")}
    for y in range(height // 5, height * 4 // 5):
        row = y * width * 3
        for x in range(width // 5, width * 4 // 5):
            r, g, b = pixels[row + 3 * x:row + 3 * x + 3]
            kind = ("purple" if r > 70 and b > 70 and g < 40 else
                    "green" if g > 60 and g > 2 * r and g > 2 * b else
                    "yellow" if r > 150 and g > 130 and b < 90 else
                    "cyan" if r < 80 and g > 150 and b > 150 else None)
            if kind:
                found[kind][0] += 1
                found[kind][1] += x
            if kind in ("yellow", "cyan") and max(
                    abs(c - e) for c, e in zip((r, g, b), YELLOW if kind == "yellow" else CYAN)) <= 8:
                found["exact"][0] += 1
    return {k: (n, total / n if n else None) for k, (n, total) in found.items()}


def live(package, templates=TEMPLATES, capture_name="materials.ppm", analyse=True):
    """The wire check and, with N3E_GRAPHICAL=1, the offscreen capture of the
    package's NPCs; returns the capture path (None without a graphical run)."""
    from isolation import DISPOSABLE_POSTGRES, container_logs, free_ports
    from readiness import wait_postgres
    from world_peer import Peer, first
    import urllib.request

    manifest = json.loads((package / "recipe.json").read_text())["manifest"]
    out = OUT / "live"
    out.mkdir(parents=True, exist_ok=True)
    server_binary = str(Path(os.environ.get("N3E_TEST_SERVER", "target/debug/n3e-server")).resolve())
    name = "n3e-pq265-" + uuid.uuid4().hex[:10]
    password = "test-only-" + uuid.uuid4().hex
    containers, server, log, capture = [], None, None, None

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
        assert set(npcs) == {t["name"] for t in templates}, npcs.keys()
        for t in templates:
            assert first(npcs[t["name"]], 31, b"").decode() == t["looks"], (t["name"], npcs[t["name"]])
        print("PASS both material templates carry their own looks key on the wire", flush=True)
        p.logout()
        if os.environ.get("N3E_GRAPHICAL") == "1":
            capture = out / capture_name
            capture.unlink(missing_ok=True)
            with open(out / "client.log", "w") as client_log:
                code = subprocess.run(
                    ["build/client/n3e-test-client", str(package), "--connect", f"localhost:{listen}", "--ca",
                     "deploy/local/ca.pem", "--auto-login", "--world-smoke", "6", "--capture", str(capture)],
                    env={**os.environ, "N3E_TEST_ACCOUNT": "explorer", "N3E_TEST_PASSWORD": password},
                    stdout=client_log, stderr=subprocess.STDOUT, timeout=120).returncode
            text = (out / "client.log").read_text()
            assert code == 0 and capture.stat().st_size > 0, (code, text[-1500:])
            runs = dict(re.findall(r"^NPC_LOOKS_RUNS looks=\d+ key=(\S+) runs=(\S+)$", text, re.M))
            if analyse:
                # Run i: first index + count : flags : source / destination factors.
                assert runs == {"demo:looks/glass": "0+36:0:0/0;36+36:1:4/5;72+6:6:0/0",
                                "demo:looks/cutout": "0+36:0:0/0;36+36:4:0/0"}, runs
                found = classify(capture)
                (purple, purple_x), (green, green_x) = found["purple"], found["green"]
                yellow, cyan, exact = found["yellow"][0], found["cyan"][0], found["exact"][0]
                assert purple > 200 and green > 200 and purple_x < green_x, found
                assert yellow > 200 and cyan > 100 and exact >= 0.8 * (yellow + cyan), found
                print(f"PASS graphical client draws NPC looks runs with their render states: blended glass "
                      f"{purple} purple px at x {purple_x:.0f}, alpha-tested hole {green} green px at x "
                      f"{green_x:.0f}, double-sided roof {cyan} cyan px, unlit {exact} of {yellow + cyan} "
                      f"yellow and cyan px at their texture's colour; {capture}", flush=True)
            else:
                print(f"capture {capture}; runs {runs}", flush=True)
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
    return capture


if __name__ == "__main__":
    os.chdir(ROOT)
    package = prepare()
    assert all((package / f"npc-looks-{i}.bin").read_bytes()[:4] == b"N3MM" for i in range(2))
    lines = npc_looks_live.check_readers(package)
    texels = 2 * ATLAS[0] * ATLAS[1] * 4
    assert any(line.startswith(f"npc looks 2 texture_bytes {texels} ") for line in lines), lines
    print(f"PASS N3MM engine 39 package: both readers accept two material looks ({texels} atlas bytes)", flush=True)
    live(package)
