"""PQ-231: an N3W2 world at map size, and N3W1/N3W2 matched-camera captures.

Original synthetic data only (tests/world_chunk_fixture.py); no KO assets and no
containers. Always: a 2048 m world of 1,183,744 vertices is written as N3W2,
cooked, admitted by the server and loaded by the client within the bounds below.
With N3E_GRAPHICAL=1 (make live) the test client also draws it offscreen, and
draws one small world cooked as N3W1 + N3L3 and as N3W2 from the same camera:
the captures must be byte-identical. The full pass of a matched capture skips
the chunk-box cull, so the large world's two passes show that the cull hides
nothing the parts' own tests would draw.

PQ-232: the client streams N3W2 chunks. The large world is drawn streamed and
all-resident (N3E_TEST_WORLD_WHOLE) from one camera, byte-identically. With a
300 m fog end, a scripted camera path across the map (N3E_TEST_WORLD_PATH) logs
the resident chunks and bytes every frame, under the client limits and never
the whole map, and the captures at the end of the path equal the all-resident
draw. A corrupt chunk in the far corner stops the client when the path reaches
it.

PQ-233: N3W2 worlds take their textures from an N3WT asset of array banks. The
small world's N3W2 capture (three banks) equals its N3W1 atlas capture. A world
whose parts name 1,201 textures cooks, is admitted and loads in four banks;
drawn with the GPU's layer limit and with a 256-layer limit (seven banks) it
gives the same captures, and a 128-layer limit (thirteen banks) or a texture
size limit below its largest texture is refused. An N3WT file declaring more
than 384 MiB of pixels is refused by the cooker and the client.
"""
import collections
import hashlib
import mmap
import os
import re
import struct
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "tests")
import world_chunk_fixture as fx  # noqa: E402
import world_chunks  # noqa: E402  (tools/assetc, on the path through the fixture)
import world_textures  # noqa: E402
import world_sequence_log  # noqa: E402

B = Path("build/world-chunks-live")
B.mkdir(parents=True, exist_ok=True)
WORK = B / "work"
# Bounds for the 2048 m world. The reference machine (PQ-231 evidence) measures
# about 2 s to write, 0.2 s to load and 180 MiB (asset check) / 280 MiB (test
# client) peak resident; the bounds leave room for a loaded gate run.
WRITE_SECONDS = 60
LOAD_MS = 5000
CHECK_RSS_MIB = 512
CLIENT_RSS_MIB = 1024
LARGE_VIEW = "1024 120 1500 1024 0 1100"
# PQ-232: from the near corner, looking into the map, 1600 m along the diagonal.
STREAM_VIEW = "100 60 100 400 0 400"
STREAM_PATH = "1600 0 1600 300"
SMALL_VIEW = "16 30 70 16 0 16"


# A small launcher forks and execs the command and reports its peak resident
# size. Linux carries the peak across exec, so a command spawned straight from
# this process (which holds the world it wrote) would report this one's.
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


# The 2048 m world, beyond every N3W1 cap.
atlas, vertices, built = fx.large()
count = len(vertices)
assert count > 1000000 and len(built["chunks"]) == 4096
start = time.monotonic()
data = world_chunks.serialize(fx.COUNT, vertices, built, (0, 0), 128, 16)
write, size = time.monotonic() - start, len(data)
assert write <= WRITE_SECONDS and 32 * 1024 * 1024 < size <= world_chunks.MAX_FILE, (write, size)
large = fx.package(WORK, "large", data)
del atlas, vertices, built, data  # keep the measured children's peak their own
code, seconds, rss, out = measured(["target/debug/n3e-server", "--check-content"], B / "large-server.log",
                                   {"N3E_PACKAGE": str(large)})
assert code == 0, out[-2000:]
code, seconds, rss, out = measured(["build/client/n3e-asset-check", str(large)], B / "large-check.log")
assert code == 0, out[-2000:]
lines = out.splitlines()
assert lines[0] == "world 0 0 1183744 2621440" and lines[1] == "world chunks 256 parts 4096", lines[:2]
assert seconds * 1000 <= LOAD_MS and rss <= CHECK_RSS_MIB, (seconds, rss)
print("PASS N3W2 2048 m world: %d vertices, %d bytes written in %.1f s; server admits it; client loads 256 "
      "chunks in %.2f s at %d MiB peak (bounds %d ms, %d MiB)"
      % (count, size, write, seconds, rss, LOAD_MS, CHECK_RSS_MIB))

# PQ-233: a world naming 1,201 textures of three sizes (and the clear one).
count, v, b = fx.many()
assert count > 1024
many = fx.package(WORK, "many", world_chunks.serialize(count, v, b, (0, 0), 36, 6),
                  textures=world_textures.serialize(fx.many_textures()))
code, _, _, out = measured(["target/debug/n3e-server", "--check-content"], B / "many-server.log",
                           {"N3E_PACKAGE": str(many)})
assert code == 0, out[-2000:]
code, _, _, out = measured(["build/client/n3e-asset-check", str(many)], B / "many-check.log")
many_pixels = sum(len(p) for c in fx.many_textures() for _, _, p in c)
assert code == 0 and ("world textures 1201 banks 4 pixels %d" % many_pixels) in out.splitlines(), out[-2000:]
# More than 384 MiB of pixels declared: 24 textures of 2048 x 2048 fill the
# bound and a 25th is refused before its pixels are read. The file is sparse
# and written straight into a package whose world names 25 textures.
heavy_package = fx.package(WORK, "heavy", fx.small_files()[2])
fx.install(heavy_package, "world.bin", world_chunks.serialize(25, *fx.small()[1:], (0, 0), 16, 2))
heavy = heavy_package / "world-textures.bin"
level = 2048 * 2048 * 4
with open(heavy, "wb") as out_file:
    out_file.write(b"N3WT" + struct.pack("<I", 25))
    for _ in range(24):
        out_file.write(struct.pack("<3I", 1, 2048, 2048))
        out_file.seek(level, 1)
    out_file.write(struct.pack("<3I", 1, 2048, 2048))
sha = hashlib.sha256()
with open(heavy, "rb") as in_file, mmap.mmap(in_file.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
    assert len(mapped) <= world_textures.MAX_FILE
    for at in range(0, len(mapped), 1 << 24):
        sha.update(mapped[at:at + (1 << 24)])
    try:
        world_textures.check(mapped)
    except ValueError as e:
        assert "world texture byte bound" in str(e), e
    else:
        raise AssertionError("cooker check admitted 400 MiB of pixels")
    size = len(mapped)
prefix, entries = fx.records(heavy_package)
entries["world-textures.bin"] = fx.string("world-textures.bin") + fx.u(size) + sha.digest()
(heavy_package / "release.bin").write_bytes(prefix + fx.u(len(entries)) + b"".join(entries[k] for k in sorted(entries)))
code, _, _, out = measured(["build/client/n3e-asset-check", str(heavy_package)], B / "heavy-check.log")
assert code != 0 and "world texture byte bound" in out, out[-2000:]
heavy.unlink()
print("PASS N3WT: a world naming %d textures cooks, is admitted and loads in 4 banks (%d pixel bytes); "
      "more than 384 MiB of declared pixels is refused by the cooker check and the client" % (count, many_pixels))

if os.environ.get("N3E_GRAPHICAL") != "1":
    print("UNVERIFIED N3W2 offscreen captures need N3E_GRAPHICAL=1 (make live)")
    sys.exit(0)

# One small world both ways, one camera: byte-identical captures.
w1, l3, w2 = fx.small_files()
captures = {}
for name, files in (("small-n3w1", (w1, l3)), ("small-n3w2", (w2,))):
    package = fx.package(WORK, name, *files)
    capture = B / (name + ".ppm")
    code, _, _, out = measured(["build/client/n3e-test-client", str(package), "--smoke", "--capture", str(capture)],
                               B / (name + "-client.log"),
                               {"N3E_TEST_WORLD_LOD": "1", "N3E_TEST_WORLD_VIEW": SMALL_VIEW})
    assert code == 0 and "PASS world LOD matched-camera captures" in out, out[-2000:]
    captures[name] = [Path(str(capture) + suffix) for suffix in (".full.ppm", ".lod.ppm")]
for one, two in zip(captures["small-n3w1"], captures["small-n3w2"]):
    assert digest(one) == digest(two), (one, two)
# The LOD pass drew coarser terrain variants and progressive states than the
# full pass, so the comparison covers level and edge selection across chunks.
assert digest(captures["small-n3w2"][0]) != digest(captures["small-n3w2"][1])
# Not an empty frame: the fog background and three lit terrain colours.
assert sum(1 for _, n in colours(captures["small-n3w2"][0]).most_common(4) if n > 5000) == 4, \
    colours(captures["small-n3w2"][0]).most_common(6)
print("PASS N3W1+N3L3 (atlas) and N3W2 (N3WT, three banks) of one world render byte-identically from one camera "
      "(full and reduced LOD passes)")

# PQ-388 (D-203): the same world as N3W5 with every terrain vertex a
# single-layer unlit vertex draws each terrain patch as its texel exactly
# (no light, no second layer; fog is 0 this near). The lit N3W2 capture from the
# same camera has none of those exact colours (n3e's light is 1.07 on flat
# ground), so the check fails with the light applied.
_, small_vertices, small_built = fx.small()
assert all(v[11] == fx.CLEAR for v in small_vertices[:16]) and small_vertices[16][4] == 0
for v in small_vertices[:16]:
    v[11] = world_chunks.UNLIT_VERTEX
w5 = world_chunks.serialize(fx.COUNT, small_vertices, small_built, (0, 0), 16, 2)
assert w5[:4] == b"N3W5"
package = fx.package(WORK, "small-n3w5", w5)
capture = B / "small-n3w5.ppm"
code, _, _, out = measured(["build/client/n3e-test-client", str(package), "--smoke", "--capture", str(capture)],
                           B / "small-n3w5-client.log", {"N3E_TEST_WORLD_LOD": "1", "N3E_TEST_WORLD_VIEW": SMALL_VIEW})
assert code == 0 and "PASS world LOD matched-camera captures" in out, out[-2000:]
texels = [bytes(c[:3]) for c in fx.COLOURS[:3]]


def exact(path):
    counted = colours(path)
    return [counted.get(t, 0) for t in texels]


unlit = [exact(Path(str(capture) + s)) for s in (".full.ppm", ".lod.ppm")]
lit = [exact(path) for path in captures["small-n3w2"]]
# The reduced pass keeps one triangle of a coarse patch, so fewer pixels.
assert all(n > 1000 for counts in unlit for n in counts), unlit
assert all(n == 0 for counts in lit for n in counts), lit
print("PASS N3W5 graphical (PQ-388, D-203): single-layer unlit terrain draws its texels exactly (%s pixels in the "
      "full pass), the lit N3W2 capture of the same world none of them" % "/".join(map(str, unlit[0])))

# PQ-394 (D-212): N3W6 texture sequences drawn over time. Two quads added to
# the small world, one opaque and unlit, one an alpha part (ONE/ZERO, unlit),
# cycle three textures each, at 10 and 7.5 fps: six solid colours no other
# surface draws exactly. The client logs every frame's
# sequence state (N3E_TEST_SEQUENCE_LOG); the check replays it in float32 from
# index 0 (index + seconds x fps, 0 at the count), so the rate and the reset are
# checked on every frame, and the frame-40 capture must hold exactly the colour
# of the frame the log names for each part and none of the other frames'. With
# a fixed frame time (N3E_TEST_SEQUENCE_SECONDS) three runs reach each part's
# three frames at the capture; the real clock, the all-resident path and the matched
# two-pass capture are checked too. The same world without the sequence bit
# (N3W4) shows only each part's first colour at every frame time.
SEQUENCE_COLOURS = [(255, 255, 0, 255), (255, 0, 255, 255), (0, 255, 255, 255),
                    (255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255)]
SEQUENCES = {6: ([4, 5, 6], 10.0), 7: ([7, 8, 9], 7.5)}  # built["chunks"] index: (slots, fps)
sequence_textures = world_textures.serialize(fx.textures() + [fx.chain(8, c) for c in SEQUENCE_COLOURS])
sequence_count = fx.COUNT + len(SEQUENCE_COLOURS)


def sequence_world(cycle):
    """The small world plus two upright 6 m quads (kind 0, two-sided) facing the
    SMALL_VIEW camera: chunks 6 (opaque, unlit) and 7 (alpha ONE/ZERO, unlit)."""
    _, v, b = fx.small()
    for index, (slots, fps) in SEQUENCES.items():
        assert len(b["chunks"]) == index
        x0, base = (7.0 if index == 6 else 19.0), len(v)
        for dx, dy in ((0, 0), (6, 0), (0, 6), (6, 6)):
            v.append([x0 + dx, 3 + dy, 20, 0, 0, 1, dx / 6, dy / 6, .5, .5, float(slots[0]), float(fx.CLEAR)])
        part = dict(center=[x0 + 3, 6, 20], radius=4.5, scale=1, kind=0,
                    flags=8 | (world_chunks.ALPHA if index == 7 else world_chunks.UNLIT),
                    levels=[(0., [base, base + 1, base + 2, base + 1, base + 3, base + 2])])
        if index == 7:
            part["alpha"] = dict(source=2, destination=1, state=0x41, point=part["center"])
        if cycle:
            part["flags"] |= world_chunks.SEQUENCE
            part["sequence"] = dict(slots=slots, fps=fps)
        b["chunks"].append(part)
    return world_chunks.serialize(sequence_count, v, b, (0, 0), 16, 2)


f32 = world_sequence_log.f32


def sequence_run(name, world, env, lod=False):
    package = fx.package(WORK, name, world, textures=sequence_textures)
    capture = B / (name + ".ppm")
    code, _, _, out = measured(["build/client/n3e-test-client", str(package), "--smoke", "--capture", str(capture)],
                               B / (name + "-client.log"),
                               {"N3E_TEST_WORLD_VIEW": SMALL_VIEW, "N3E_TEST_SEQUENCE_LOG": "1",
                                **({"N3E_TEST_WORLD_LOD": "1"} if lod else {}), **env})
    assert code == 0 and (not lod or "PASS world LOD matched-camera captures" in out), out[-2000:]
    return out, ([Path(str(capture) + s) for s in (".full.ppm", ".lod.ppm")] if lod else [capture])


def exact_colours(path):
    counted = colours(path)
    return [counted.get(bytes(c[:3]), 0) for c in SEQUENCE_COLOURS]


def check_sequence(name, world, env, lod=False, cycle=True):
    """{chunks index: frame drawn at the capture} after checking the log against
    the replay and the capture(s) against the logged frame."""
    out, paths = sequence_run(name, world, env, lod)
    rows = world_sequence_log.rows(out)
    if not cycle:
        assert not rows, (name, list(rows))
        at_capture = {index: 0 for index in SEQUENCES}
    else:
        assert len(rows) == 2, (name, list(rows))
        at_capture = {}
        for part_rows in rows.values():
            (index,) = [i for i, (_, fps) in SEQUENCES.items() if float(part_rows[0]["fps"]) == fps]
            assert int(part_rows[0]["frames"]) == len(SEQUENCES[index][0])
            shown = world_sequence_log.replay(part_rows)
            # The matched two-pass capture is taken once the stream settles,
            # the smoke capture at frame 40.
            matched = [int(r["frame"]) for r in part_rows if r["matched"] == "1"]
            assert len(matched) == (1 if lod else 0), (name, matched)
            at = matched[0] if lod else 40
            assert at in shown, (name, sorted(shown))
            at_capture[index] = shown[at]
    for path in paths:
        counts = exact_colours(path)
        for index, (slots, _) in SEQUENCES.items():
            # The matched pair is captured inside the world pass, before the
            # alpha parts draw (PQ-398), so it holds only the opaque quad.
            shown = at_capture[index] if not (lod and index == 7) else None
            for k, slot in enumerate(slots):
                n = counts[slot - fx.COUNT]
                assert (n > 40) if k == shown else (n == 0), (name, path, index, k, counts)
    return at_capture, counts, rows

def client(package, name, env, expect_pass=True):
    """Run the test client on `package`: (exit code, peak MiB, output, capture stem)."""
    capture = B / (name + ".ppm")
    code, _, rss, out = measured(["build/client/n3e-test-client", str(package), "--smoke", "--capture", str(capture)],
                                 B / (name + "-client.log"), {"N3E_TEST_WORLD_LOD": "1", **env})
    if expect_pass:
        assert code == 0 and "PASS world LOD matched-camera captures" in out, out[-2000:]
    return code, rss, out, capture


def pair(capture):
    return [Path(str(capture) + s) for s in (".full.ppm", ".lod.ppm")]


def stream_rows(out):
    return [dict(f.split("=", 1) for f in line.split()[1:]) for line in out.splitlines()
            if line.startswith("WORLD_STREAM ")]


LIMIT_CHUNKS, LIMIT_BYTES = 1024, 256 * 1024 * 1024

# The large world from one camera, streamed and all-resident.
_, rss, out, capture = client(large, "large", {"N3E_TEST_WORLD_VIEW": LARGE_VIEW})
_, whole_rss, whole_out, whole = client(large, "large-whole", {"N3E_TEST_WORLD_VIEW": LARGE_VIEW, "N3E_TEST_WORLD_WHOLE": "1"})
load = int(re.search(r"^WORLD_LOAD chunks=256 vertices=1183744 indices=7864320 ms=(\d+)$", whole_out, re.M).group(1))
index = int(re.search(r"^WORLD_LOAD chunks=256 vertices=0 indices=0 ms=(\d+) streamed$", out, re.M).group(1))
# The last two detail lines are the matched passes (frame 40 also prints one).
passes = re.findall(r"^WORLD_DETAIL visible=(\d+) .* chunks=(\d+)/256$", out, re.M)[-2:]
whole_passes = re.findall(r"^WORLD_DETAIL visible=(\d+) .* chunks=(\d+)/256$", whole_out, re.M)[-2:]
assert len(passes) == 2 and len(whole_passes) == 2 and whole_passes[0][1] == "256", (passes, whole_passes)
# The no-cull pass draws every resident chunk; the same parts either way.
assert passes[0][0] == passes[1][0] == whole_passes[0][0] == whole_passes[1][0], (passes, whole_passes)
assert passes[1][1] == whole_passes[1][1] and 0 < int(passes[1][1]) < 256, (passes, whole_passes)
full, lod = pair(capture)
assert digest(full) == digest(lod), "the chunk-box cull changed the image"
for one, two in zip(pair(capture), pair(whole)):
    assert digest(one) == digest(two), ("streamed and all-resident draws differ", one, two)
assert load <= LOAD_MS and index <= LOAD_MS and max(rss, whole_rss) <= CLIENT_RSS_MIB, (load, index, rss, whole_rss)
settled = stream_rows(out)[-1]
print("PASS N3W2 graphical: 2048 m world all-resident load %d ms, %d MiB peak; streamed index %d ms, %d MiB peak "
      "(bounds %d ms, %d MiB), %s chunks resident when settled; %s of 256 chunks drawn, %s parts, image unchanged by "
      "the chunk-box cull and equal to the all-resident draw"
      % (load, whole_rss, index, rss, LOAD_MS, CLIENT_RSS_MIB, settled["resident"], passes[1][1], passes[0][0]))

# A camera path across the map with a 300 m fog end: bounded residency.
stream = fx.package(WORK, "large-stream", (large / "world.bin").read_bytes(), fog_end=300)
path = {"N3E_TEST_WORLD_VIEW": STREAM_VIEW, "N3E_TEST_WORLD_PATH": STREAM_PATH}
_, rss, out, capture = client(stream, "stream", path)
_, whole_rss, _, whole = client(stream, "stream-whole", {**path, "N3E_TEST_WORLD_WHOLE": "1"})
rows = stream_rows(out)
frames = int(STREAM_PATH.split()[3])
assert len(rows) >= frames, len(rows)
resident = [int(r["resident"]) for r in rows]
peak = max(int(r["max"].split("/")[0]) for r in rows), max(int(r["max"].split("/")[1]) for r in rows)
assert all(int(r["bytes"]) <= LIMIT_BYTES and int(r["resident"]) <= LIMIT_CHUNKS for r in rows)
assert peak[0] <= LIMIT_CHUNKS and peak[1] <= LIMIT_BYTES and peak[0] < 256, peak
assert int(rows[-1]["evicted"]) > 0 and all(r["limited"] == "0" for r in rows), rows[-1]
assert rows[-1]["settled"] == "1" and rows[-1]["missing"] == "0", rows[-1]
late = sum(1 for r in rows if r["missing"] != "0")
# Not an empty frame: the fog background and the three terrain colours.
assert sum(1 for _, n in colours(pair(capture)[0]).most_common(4) if n > 5000) == 4, \
    colours(pair(capture)[0]).most_common(6)
for one, two in zip(pair(capture), pair(whole)):
    assert digest(one) == digest(two), ("streamed path end and all-resident draw differ", one, two)
print("PASS N3W2 streaming path: %d frames across the 2048 m map at fog 300 keep %d-%d of 256 chunks resident "
      "(peak %d chunks, %.1f MiB incl. in flight; limits %d, %d MiB), %s evicted, %d frames with a visible chunk "
      "still loading; %d MiB peak against %d MiB all-resident; captures at the path end equal the all-resident draw"
      % (len(rows), min(resident), max(resident), peak[0], peak[1] / 1048576, LIMIT_CHUNKS, LIMIT_BYTES >> 20,
         rows[-1]["evicted"], late, rss, whole_rss))

# 4096 one-metre chunks, all in reach: the client keeps the nearest 1024 and
# says once, in both builds, that the rest are not drawn (review, PQ-232).
a, v, b = fx.plain(64, 1, 2)
tiny = fx.package(WORK, "tiny", world_chunks.serialize(fx.COUNT, v, b, (0, 0), 1, 64), fog_end=300)
code, _, out, _ = client(tiny, "tiny", {"N3E_TEST_WORLD_VIEW": "32 20 0 32 0 32"}, expect_pass=False)
rows = stream_rows(out)
notice = re.findall(r"^world streaming: (\d+) chunks in reach exceed the client limits \(1024 chunks, 256 MiB\); "
                    r"the farthest are not drawn$", out, re.M)
assert code == 0 and len(notice) == 1 and int(notice[0]) > 0, out[-2000:]
assert rows and max(int(r["max"].split("/")[0]) for r in rows) == LIMIT_CHUNKS, rows[-1:]
print("PASS N3W2 streaming: 4096 one-metre chunks in reach hold the 1024-chunk limit with one notice (%s left out)"
      % notice[0])

# The same path with the far corner chunk corrupted (and rehashed): the client
# streams the start and stops when the path reaches the corner.
data = bytearray((stream / "world.bin").read_bytes())
x, z, start, _ = fx.chunk_body(bytes(data))[-1]
assert (x, z) == (15, 15)
struct.pack_into("<I", data, start, 0)  # vertex count 0: below the bound
fx.install(stream, "world.bin", bytes(data))
code, _, out, _ = client(stream, "stream-corrupt", path, expect_pass=False)
rows = stream_rows(out)
assert code != 0 and "viewer: world chunk 15,15: cooked count" in out, out[-2000:]
assert frames // 2 < len(rows) <= frames and "PASS world LOD" not in out, len(rows)
print("PASS N3W2 streaming: a corrupt chunk in the far corner stops the client when reached (frame %d of %d)"
      % (len(rows), frames))

# PQ-233: the 1,201-texture world drawn with the GPU's layer limit (four banks)
# and with a 256-layer limit (seven banks): the same image, so every texture
# keeps its pixels whichever bank holds it. Lower limits are refused.
MANY_VIEW = "108 150 108 108 0 109"
_, _, out, capture = client(many, "many", {"N3E_TEST_WORLD_VIEW": MANY_VIEW})
assert "WORLD_TEXTURES textures=1201 banks=4 " in out, out[-2000:]
_, _, split_out, split = client(many, "many-split", {"N3E_TEST_WORLD_VIEW": MANY_VIEW, "N3E_TEST_WORLD_TEXTURE_LAYERS": "256"})
assert "WORLD_TEXTURES textures=1201 banks=7 " in split_out, split_out[-2000:]
for one, two in zip(pair(capture), pair(split)):
    assert digest(one) == digest(two), ("bank split changed the image", one, two)
shown = sum(1 for _, n in colours(pair(capture)[0]).items() if n >= 20)
assert shown >= 300, shown
code, _, out, _ = client(many, "many-layers", {"N3E_TEST_WORLD_VIEW": MANY_VIEW, "N3E_TEST_WORLD_TEXTURE_LAYERS": "128"},
                         expect_pass=False)
assert code != 0 and ("world textures need 13 array banks of at most 128 layers on this GPU; the client binds 8"
                      in out), out[-2000:]
code, _, out, _ = client(many, "many-size", {"N3E_TEST_WORLD_VIEW": MANY_VIEW, "N3E_TEST_WORLD_TEXTURE_SIZE": "16"},
                         expect_pass=False)
assert code != 0 and "world texture 32x32 exceeds the GPU texture size limit 16" in out, out[-2000:]
print("PASS N3WT graphical: 1,201 textures in 4 banks and in 7 (256-layer limit) draw the same image with %d colours "
      "shown; a 128-layer limit (13 banks) and a 16-texel size limit are refused" % shown)

# PQ-387 (D-204): N3WO maps over the near terrain around the eye, on the 128 m
# terrain world (4 x 4 patches of 8 four-metre tiles, 1298's patch and block
# sizes), as N3W1 + N3L3 and as N3W2 (streamed). Maps: block (2, 2) red at
# alpha 255 and block (1, 2) black at alpha 136 in patches (1, 1) and (0, 1);
# block (3, 2) magenta at alpha 0; block (6, 6) black at alpha 255 in patch
# (3, 3). Each run draws one frame without and then with the maps (pass 0 / 1).
import ko_lod  # noqa: E402
import world_overlay  # noqa: E402

LIGHT = dict(patch_tiles=8, block_tiles=4, window=1, side=32, cell=8, inset=1, levels=4, width=8)


def solid(rgba):
    return [bytes(rgba) * ((32 >> k) ** 2) for k in range(4)]


overlay_maps = {(2, 2): solid((255, 0, 0, 255)), (1, 2): solid((0, 0, 0, 136)),
                (3, 2): solid((255, 0, 255, 0)), (6, 6): solid((0, 0, 0, 255))}
overlay = world_overlay.serialize(LIGHT, overlay_maps)
t_atlas, t_vertices, t_built, t_hf, t_roof = fx.terrain()
# A near radius of 3 patches (1298's grows with the far plane from 2): patch
# (3, 3) is drawn at its near level from patch (1, 1) too, so only the eye's
# window keeps its map off.
t_built["terrain_lod"]["minimum"] = 3
t_w1 = fx.n3w1(t_atlas, t_vertices, [0, 1, 2])
t_ox, t_oz, t_side = world_chunks.grid(t_built, 32)
t_w2 = world_chunks.serialize(fx.COUNT, t_vertices, t_built, (t_ox, t_oz), 32, t_side)
overlay_packages = {
    "overlay-n3w1": fx.package(WORK, "overlay-n3w1", t_w1, ko_lod.serialize(t_built), heightfield=t_hf,
                               triangles=t_roof, overlay=overlay),
    "overlay-n3w2": fx.package(WORK, "overlay-n3w2", t_w2, heightfield=t_hf, triangles=t_roof, overlay=overlay)}
# The eye in patch (1, 1) (x -30, reference z (64 - 30) / 4 = 8.5 tiles), and in
# patch (3, 3), looking down on the whole map from 130 m (fog starts at 200 m).
OVERLAY_VIEWS = {"near": "-24 130 24 -8 0 8", "far": "40 130 -40 24 0 -24"}


def overlay_client(package, name, view, extra=None):
    capture = B / (name + ".ppm")
    code, _, _, out = measured(["build/client/n3e-test-client", str(package), "--smoke", "--capture", str(capture)],
                               B / (name + "-client.log"),
                               {"N3E_TEST_WORLD_OVERLAY": "1", "N3E_TEST_WORLD_VIEW": view, **(extra or {})})
    assert code == 0 and "PASS world overlay matched-camera captures" in out, out[-2000:]
    rows = re.findall(r"^WORLD_OVERLAY pass=(\d) patches=(\d+) centre=(-?\d+),(-?\d+) uploads=\d+ withheld=(\d+)$",
                      out, re.M)[-2:]
    return [Path(str(capture) + s) for s in (".no-overlay.ppm", ".overlay.ppm")], rows


def pixels(path):
    data = path.read_bytes().split(b"\n", 3)[3]
    return [data[i:i + 3] for i in range(0, len(data), 3)]


def classes(path):
    px = pixels(path)
    return dict(red=sum(1 for p in px if p[0] > 100 and p[1] < 30 and p[2] < 30),
                black=sum(1 for p in px if p == b"\0\0\0"),
                magenta=sum(1 for p in px if p[0] > 100 and p[2] > 100 and p[1] < 30))


def half(no, yes):
    """Median of overlay / plain brightness over changed pixels that are not red."""
    ratios = sorted(sum(b) / sum(a) for a, b in zip(pixels(no), pixels(yes))
                    if a != b and sum(a) > 60 and not (b[0] > 100 and b[1] < 30 and b[2] < 30))
    return len(ratios), ratios[len(ratios) // 2] if ratios else 0


overlay_captures = {}
for name, package in overlay_packages.items():
    for view, camera in OVERLAY_VIEWS.items():
        overlay_captures[(name, view)] = overlay_client(package, "%s-%s" % (name, view), camera)
for view in OVERLAY_VIEWS:
    (one, rows_one), (two, rows_two) = overlay_captures[("overlay-n3w1", view)], overlay_captures[("overlay-n3w2", view)]
    for a, b in zip(one, two):
        assert digest(a) == digest(b), ("N3W1 and N3W2 overlay draws differ", view, a, b)
    assert rows_one == rows_two, (rows_one, rows_two)
(near_plain, near_lit), near_rows = overlay_captures[("overlay-n3w1", "near")]
(far_plain, far_lit), far_rows = overlay_captures[("overlay-n3w1", "far")]
near, far = classes(near_lit), classes(far_lit)
assert classes(near_plain) == classes(far_plain) == dict(red=0, black=0, magenta=0), (classes(near_plain), classes(far_plain))
# Near: the eye's window (patches 0..2) draws the red and the half-alpha maps,
# not the far black one; the alpha-0 map draws nothing.
assert near_rows[0][:2] == ("0", "0") and near_rows[1][0] == "1" and int(near_rows[1][1]) >= 2, near_rows
assert near_rows[1][2:4] == ("1", "1") and far_rows[1][2:4] == ("3", "3"), (near_rows, far_rows)
# The window, not the level of detail, keeps the other view's map off: each
# view draws a near-level patch with maps outside its window (patch (3, 3)
# from (1, 1), and (1, 1) and (0, 1) from (3, 3)), which the client counts as
# withheld. Without that the black / red checks below would test nothing.
assert int(near_rows[1][4]) >= 1 and int(far_rows[1][4]) >= 1, (near_rows, far_rows)
assert near["red"] > 1000 and near["black"] == 0 and near["magenta"] == 0, near
changed, ratio = half(near_plain, near_lit)
# Source alpha over one minus source alpha at 136: 1 - 136 / 255 of the ground.
assert changed > 1000 and abs(ratio - (1 - 136 / 255)) < .02, (changed, ratio)
# Far: the window follows the eye to patch (3, 3), which draws the black map
# whole and not the red one, now two patches away.
assert far["black"] > 1000 and far["red"] == 0 and far["magenta"] == 0, far
print("PASS N3WO graphical (PQ-387, D-204): near terrain maps drawn only in the eye's 3 x 3 patch window, the "
      "same as N3W1 + N3L3 and as N3W2: from patch (1, 1) %d red pixels, the half-alpha map at %.3f of the "
      "ground (%d pixels; 1 - 136/255 = %.3f), no pixel of the far alpha-255 black map; from patch (3, 3) %d "
      "black pixels and no red; alpha 0 draws nothing; the frame without the maps has none of them"
      % (near["red"], ratio, changed, 1 - 136 / 255, far["black"]))


cycled, plain = sequence_world(True), sequence_world(False)
assert cycled[:4] == b"N3W6" and plain[:4] == b"N3W4", (cycled[:4], plain[:4])
reached, pixels = {}, {}
for seconds in ("0.01", "0.025", "0.03"):
    frames, counts, rows = check_sequence("sequence-" + seconds, cycled, {"N3E_TEST_SEQUENCE_SECONDS": seconds})
    reached[seconds], pixels[seconds] = frames, counts
    assert all(f32(float(r["seconds"])) == f32(float(seconds)) for part in rows.values() for r in part)
    # Over the run each part shows every frame of its cycle (40 advances at
    # 0.1 frames each or more).
    for part in rows.values():
        assert {int(r["frame_index"]) for r in part} == {0, 1, 2}, (seconds, part[-1])
for index in SEQUENCES:
    assert {reached[s][index] for s in reached} == {0, 1, 2}, reached
real, _, real_rows = check_sequence("sequence-clock", cycled, {})
assert all(0.001 < float(r["seconds"]) < 1.0 or float(r["seconds"]) == f32(1 / 30)
           for part in real_rows.values() for r in part)
whole, _, _ = check_sequence("sequence-whole", cycled, {"N3E_TEST_SEQUENCE_SECONDS": "0.025",
                                                         "N3E_TEST_WORLD_WHOLE": "1"})
assert whole == reached["0.025"], (whole, reached)
paired, _, _ = check_sequence("sequence-lod", cycled, {"N3E_TEST_SEQUENCE_SECONDS": "0.025"}, lod=True)
for seconds in ("0.025", "0.03"):
    check_sequence("sequence-off-" + seconds, plain, {"N3E_TEST_SEQUENCE_SECONDS": seconds}, cycle=False)
print("PASS N3W6 graphical (PQ-394, D-212): an opaque and an alpha sequence part replay index + seconds x fps "
      "with the reset to 0 on every logged frame and draw the logged frame exactly at the capture "
      "(frames at 0.01 / 0.025 / 0.03 s: %s; real clock %s; the all-resident path agrees, and both passes of a "
      "matched capture draw the opaque one's logged frame); "
      "without the bit only the first frames draw" % (
          " / ".join("%d,%d" % (reached[s][6], reached[s][7]) for s in ("0.01", "0.025", "0.03")),
          "%d,%d" % (real[6], real[7])))
