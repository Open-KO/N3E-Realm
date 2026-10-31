"""PQ-234: the KO bake writes N3W2 for a map that does not fit N3W1.

Original synthetic data only (tools/assetc/ko_large_zone_fixture.py); no KO
assets and no containers. Always: a 513-sample (2048 m) GTD with its colour map
(TCT), DTex tiles and an OPD of textured placements is baked by
`ko_scene.bake_world`, which reads it past ko_terrain's 129-sample cap and writes
N3W2 chunks with N3WT textures; the package cooks with N3C2 collision, the
server admits it and the client loads it. A 33-sample map whose 330 object
textures overflow N3W1's atlas is rebuilt the same way and loads too.

With N3E_GRAPHICAL=1 (make live) the test client draws the 2048 m world
offscreen from one camera, streamed and all-resident: the captures are equal,
show the tile, colour-map and object textures, and the reduced-LOD pass draws
coarser terrain than the full pass.
"""
import collections
import hashlib
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "tests")
sys.path.insert(0, "tools/assetc")
import world_chunk_fixture as fx  # noqa: E402  (puts tools/assetc on the path)
import ko_large_zone_fixture as zone_fixture  # noqa: E402
import ko_scene  # noqa: E402
import world_textures  # noqa: E402

B = Path("build/ko-world-live")
B.mkdir(parents=True, exist_ok=True)
WORK = B / "work"
# The reference machine (PQ-234 evidence) bakes the 2048 m fixture in about
# 12 s at 1 GiB peak and loads it in under 1 s; the bounds leave room for a
# loaded gate run.
BAKE_SECONDS = 240
LOAD_MS = 5000
CHECK_RSS_MIB = 768
# Inside the map (centred on the origin), looking across lattice placements.
VIEW = "60 45 250 0 0 0"
LAUNCH = """import os, sys
pid = os.fork()
if pid == 0:
    os.execvp(sys.argv[1], sys.argv[1:])
_, status, usage = os.wait4(pid, 0)
print("PEAK_KIB", usage.ru_maxrss, flush=True)
sys.exit(os.waitstatus_to_exitcode(status))
"""


def measured(cmd, log, env=None):
    """Run to completion: (exit code, seconds, peak resident MiB, output)."""
    start = time.monotonic()
    with open(log, "w") as out:
        code = subprocess.run([sys.executable, "-I", "-c", LAUNCH, *cmd], env={**os.environ, **(env or {})},
                              stdout=out, stderr=subprocess.STDOUT).returncode
    seconds, text = time.monotonic() - start, Path(log).read_text()
    peak = re.search(r"^PEAK_KIB (\d+)$", text, re.M)
    return code, seconds, int(peak.group(1)) // 1024 if peak else 1 << 30, text


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def colours(path):
    data = path.read_bytes()
    lines = data.split(b"\n", 3)
    assert lines[0] == b"P6" and lines[2] == b"255", path
    pixels = lines[3]
    return collections.Counter(pixels[i:i + 3] for i in range(0, len(pixels), 3))


def bake(name, samples, object_textures):
    zone = zone_fixture.write(WORK / (name + "-zone"), samples, object_textures)
    start = time.monotonic()
    world = ko_scene.bake_world(zone["gtd"], zone["opd"], zone["assets"], zone["tct"])
    return zone, world, time.monotonic() - start


def admitted(name, world):
    """Cook `world` into a demo-based package; the server and the client accept
    it. Returns (package, asset-check output, seconds, peak MiB)."""
    package = fx.package(WORK, name, world["world"], heightfield=world["heightfield"],
                         triangles=world["triangles"], textures=world["textures"], fog_end=400)
    collision = (package / "collision.bin").read_bytes()
    assert collision[:4] == b"N3C2", collision[:4]
    code, _, _, out = measured(["target/debug/n3e-server", "--check-content"], B / (name + "-server.log"),
                               {"N3E_PACKAGE": str(package)})
    assert code == 0, out[-2000:]
    code, seconds, rss, out = measured(["build/client/n3e-asset-check", str(package)], B / (name + "-check.log"))
    assert code == 0, out[-2000:]
    return package, out.splitlines(), seconds, rss


def expect_world(lines, built, textures):
    count, banks, pixels = world_textures.check(textures)
    parts = len(built["chunks"])
    chunks = [line for line in lines if line.startswith("world chunks ")]
    assert len(chunks) == 1 and re.fullmatch(r"world chunks \d+ parts %d" % parts, chunks[0]), (chunks, parts)
    assert ("world textures %d banks %d pixels %d" % (count, banks, pixels)) in lines, lines[:6]
    return int(chunks[0].split()[2]), count, banks


# The 2048 m map: beyond ko_terrain's 129-sample cap and N3W1's vertex cap.
zone, world, seconds = bake("large", 513, 2)
built, report = world["built"], world["report"]
terrain = built["report"]["terrain_vertices"]
# PQ-382 (D-202): the zone's opaque object parts set the cut-at-zero bit: N3W4.
assert world["chunked"] and world["lod"] is None and world["world"][:4] == b"N3W4"
assert world["heightfield"]["width"] == 513 and terrain == 512 * 512 * 4 > ko_scene.MAX_VERTICES, terrain
expected = 1 + zone["tile_textures"] + zone["color_textures"] + zone["object_textures"]
assert built["texture_count"] == report["world_textures"]["textures"] == expected == 267, built["texture_count"]
patches = sum(1 for p in built["chunks"] if p.get("kind") == 2)
assert patches == 64 * 64 and built["report"]["objects"]["placements"] == zone["shapes"] == 256
assert seconds <= BAKE_SECONDS, seconds
large, lines, load, rss = admitted("large", world)
chunk_count, texture_count, banks = expect_world(lines, built, world["textures"])
assert chunk_count == 256 and load * 1000 <= LOAD_MS and rss <= CHECK_RSS_MIB, (chunk_count, load, rss)
print("PASS KO bake N3W2: a synthetic 513-sample zone (%d terrain vertices, %d terrain patches, %d placements) "
      "bakes in %.1f s to %d chunks and %d N3WT textures in %d banks with N3C2 collision; the server admits it and "
      "the client loads it in %.2f s at %d MiB peak (bounds %d s, %d ms, %d MiB)"
      % (terrain, patches, zone["shapes"], seconds, chunk_count, texture_count, banks, load, rss,
         BAKE_SECONDS, LOAD_MS, CHECK_RSS_MIB))
del world, built

# A 33-sample map within the cap whose 330 object textures overflow the atlas.
zone, world, _ = bake("overflow", 33, 330)
assert world["chunked"] and world["world"][:4] == b"N3W4", world["report"].get("n3w1_refused")
assert world["report"]["n3w1_refused"] == "world atlas overflow at 324 slots", world["report"]
_, lines, _, _ = admitted("overflow", world)
_, texture_count, _ = expect_world(lines, world["built"], world["textures"])
assert texture_count == 1 + 8 + 1 + 330, texture_count
print("PASS KO bake fallback: a 33-sample map whose objects overflow N3W1 (%s) is rebuilt as N3W2 with %d N3WT "
      "textures, cooked and loaded" % (world["report"]["n3w1_refused"], texture_count))
del world

if os.environ.get("N3E_GRAPHICAL") != "1":
    print("UNVERIFIED KO N3W2 offscreen captures need N3E_GRAPHICAL=1 (make live)")
    sys.exit(0)


def client(name, env):
    capture = B / (name + ".ppm")
    code, _, rss, out = measured(["build/client/n3e-test-client", str(large), "--smoke", "--capture", str(capture)],
                                 B / (name + "-client.log"), {"N3E_TEST_WORLD_LOD": "1", "N3E_TEST_WORLD_VIEW": VIEW,
                                                              **env})
    assert code == 0 and "PASS world LOD matched-camera captures" in out, out[-2000:]
    assert ("WORLD_TEXTURES textures=%d banks=%d " % (texture_count_large, banks)) in out, out[-2000:]
    return out, [Path(str(capture) + s) for s in (".full.ppm", ".lod.ppm")]


texture_count_large = expected
out, streamed = client("large", {})
_, whole = client("large-whole", {"N3E_TEST_WORLD_WHOLE": "1"})
for one, two in zip(streamed, whole):
    assert digest(one) == digest(two), ("streamed and all-resident draws differ", one, two)
# The reduced pass picked coarser terrain levels (the colour map) somewhere.
assert digest(streamed[0]) != digest(streamed[1])
drawn = re.findall(r"^WORLD_DETAIL visible=(\d+) .* chunks=(\d+)/256$", out, re.M)[-1]
assert 0 < int(drawn[1]) < 256, drawn
# Not an empty frame: fog, terrain tiles and objects in many shades.
shades = sum(1 for _, n in colours(streamed[0]).items() if n >= 50)
assert shades >= 100, shades
print("PASS KO N3W2 graphical: the baked 2048 m zone draws %s of 256 chunks (%s parts) with %d shades, streamed "
      "equal to all-resident, the reduced-LOD pass coarser than the full pass" % (drawn[1], drawn[0], shades))
