"""PQ-387 (D-204): N3WO, the maps an engine blends over the near terrain around
the eye, and the KO reader that writes it from a zone's `.tlt` light maps.

Original synthetic data only (no KO bytes): world_chunk_fixture's 128 m terrain
world (4 x 4 patches of 8 x 8 four-metre tiles) and hand-built `.tlt` files.

* The format: serialize / check round trip, and each bound refused by the
  cooker check and, through a release, by the client.
* `ko_light_maps`: a `.tlt` read as 1298's `0059ba90` / `0059c450` read it
  (version, patch table pz * P + px, offset above 0, count above 0, int32 tx,
  tz and an N3 texture per entry; block (2 px + tx, 2 pz + tz)), A4R4G4B4
  decoded to RGBA8 with every mip level; n3e's fail-closed refusals; a zone
  without maps gives no overlay.
* A package: the cooker takes `world_overlay` with a world and exploration
  whose terrain policy its grid covers; the client's asset check loads it
  (`world overlay maps ...`) and the server admits it; a grid that differs
  from the terrain policy, a bad magic, an overlay without a world, and
  trailing bytes are refused by the cooker, the client and (magic,
  compatibility) the server.
"""
import json
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "tests")
import world_chunk_fixture as fx  # noqa: E402  (puts tools/assetc on the path)
import ko_lod  # noqa: E402
import ko_light_maps  # noqa: E402
import main  # noqa: E402
import world_overlay  # noqa: E402

B = Path("build/world-overlay")
shutil.rmtree(B, ignore_errors=True)
B.mkdir(parents=True)


def refused(fn, *args, **kw):
    try:
        fn(*args, **kw)
    except ValueError as error:
        return str(error)
    raise AssertionError("accepted: %s%r" % (fn.__name__, args))


# --- the format -----------------------------------------------------------------
KO = dict(patch_tiles=8, block_tiles=4, window=1, side=32, cell=8, inset=1, levels=4, width=8)


def solid(rgba, side=32, levels=4):
    return [bytes(rgba) * ((side >> k) ** 2) for k in range(levels)]


maps = {(3, 2): solid((255, 0, 0, 255)), (1, 0): solid((0, 0, 0, 136)), (7, 7): solid((0, 0, 0, 255))}
data = world_overlay.serialize(KO, maps)
header, keys = world_overlay.check(data)
assert header == dict(KO, count=3) and keys == [(1, 0), (3, 2), (7, 7)], (header, keys)
assert len(data) == world_overlay.HEADER + 3 * (8 + world_overlay.map_bytes(32, 4))
for change, phrase in ((dict(block_tiles=3), "grid"), (dict(patch_tiles=0), "grid"), (dict(block_tiles=1), "grid"),
                       (dict(window=3), "window"), (dict(cell=7), "texel layout"), (dict(side=48, cell=12), "texel layout"),
                       (dict(inset=4), "texel layout"), (dict(levels=7), "levels"), (dict(levels=0), "levels"),
                       (dict(width=0), "width")):
    assert phrase in refused(world_overlay.serialize, dict(KO, **change), maps), change
assert "block" in refused(world_overlay.serialize, KO, {(8, 0): solid((0, 0, 0, 1))})
assert "map size" in refused(world_overlay.serialize, KO, {(0, 0): solid((0, 0, 0, 1), levels=3)})
assert "count" in refused(world_overlay.serialize, KO, {})
assert "size" in refused(world_overlay.check, data + b"\0")
assert "size" in refused(world_overlay.check, data[:-1])
assert "magic" in refused(world_overlay.check, b"N3WX" + data[4:])
step = 8 + world_overlay.map_bytes(32, 4)
first, second = world_overlay.HEADER, world_overlay.HEADER + step
swapped = data[:first] + data[second:second + step] + data[first:second] + data[second + step:]
assert "order" in refused(world_overlay.check, swapped)
twice = data[:second] + data[first:second] + data[second + step:]
assert "order" in refused(world_overlay.check, twice)
print("PASS N3WO format: header, block order and level sizes round trip; grid, window, texel layout, "
      "levels, width, block, map size, count, trailing and missing bytes, magic and block order refused")


# --- ko_light_maps on a synthetic .tlt -------------------------------------------
def n3_texture(side, texel, mips=True, fmt=26, name=b"lm"):
    """An N3 texture record (NTF3) of A4R4G4B4 levels from side down to 4."""
    out = struct.pack("<i", len(name)) + name + b"NTF\x03" + struct.pack("<4i", side, side, fmt, int(mips))
    s = side
    while True:
        out += struct.pack("<H", texel) * (s * s)
        if not mips or s <= 4:
            return out
        s //= 2


def tlt(patches, entries, version=0):
    """entries: {patch index: [(tx, tz, texture bytes)]} (or an int: that
    address); the rest get address 0."""
    table = [0] * (patches * patches)
    body = bytearray()
    at = 4 + 4 * len(table)
    for index, entry in sorted(entries.items()):
        if isinstance(entry, int):
            table[index] = entry
            continue
        table[index] = at + len(body)
        body += struct.pack("<i", len(entry))
        for tx, tz, texture in entry:
            body += struct.pack("<2i", tx, tz) + texture
    return struct.pack("<i", version) + struct.pack("<%di" % len(table), *table) + bytes(body)


BLACK = 0x8000             # A4R4G4B4: alpha 8 (136), black
PALE = (9 << 12) | 0xDD9   # alpha 9 (153), nibbles (13, 13, 9) as elmo2004's commonest
path = B / "zone.tlt"
# 17 samples: P = 2. Patch 0 (0, 0) has blocks (0, 0) and (1, 1); patch 1 (1, 0) none
# (address 0); patch 2 (0, 1) a negative address; patch 3 (1, 1) a count of 0.
path.write_bytes(tlt(2, {0: [(0, 0, n3_texture(32, BLACK)), (1, 1, n3_texture(32, PALE))], 2: -5,
                         3: []}))
read, report = ko_light_maps.load(path, 17)
assert sorted(read) == [(0, 0), (1, 1)] and report["maps"] == 2 and report["patches_with_maps"] == 1, report
assert [len(level) for level in read[(0, 0)]] == [32 * 32 * 4, 16 * 16 * 4, 8 * 8 * 4, 4 * 4 * 4]
assert read[(0, 0)][0][:4] == bytes((0, 0, 0, 136)) and read[(1, 1)][3][:4] == bytes((221, 221, 153, 153))
assert report["max_alpha"] == 153 and report["coloured_base_texels"] == 32 * 32, report
patch_3 = tlt(2, {3: [(1, 0, n3_texture(32, BLACK))]})
path.write_bytes(patch_3)
assert sorted(ko_light_maps.load(path, 17)[0]) == [(3, 2)]  # (2 * 1 + 1, 2 * 1 + 0)
overlay, _ = ko_light_maps.overlay(path, 17)
assert world_overlay.check(overlay)[0] == dict(KO, width=4, count=1)
path.write_bytes(tlt(2, {2: -5}))
assert ko_light_maps.overlay(path, 17) == (None, ko_light_maps.load(path, 17)[1])
for entries, version, phrase in (({0: [(0, 0, n3_texture(32, BLACK))]}, 1, "version 1"),
                                 ({0: [(2, 0, n3_texture(32, BLACK))]}, 0, "names block (2, 0)"),
                                 ({0: [(0, -1, n3_texture(32, BLACK))]}, 0, "names block (0, -1)"),
                                 ({0: [(0, 0, n3_texture(32, BLACK)), (0, 0, n3_texture(32, BLACK))]}, 0, "twice"),
                                 ({0: [(0, 0, n3_texture(16, BLACK))]}, 0, "not 32x32"),
                                 ({0: [(0, 0, n3_texture(32, BLACK)), (1, 0, n3_texture(32, BLACK, mips=False))]}, 0,
                                  "mip chain differs"),
                                 ({0: [(0, 0, n3_texture(32, 0, fmt=0x31545844))]}, 0, "not a pixel format"),
                                 ({0: 10 ** 6}, 0, "past the file")):
    path.write_bytes(tlt(2, entries, version))
    assert phrase in refused(ko_light_maps.load, path, 17), (phrase, refused(ko_light_maps.load, path, 17))
path.write_bytes(tlt(2, {0: [(0, 0, n3_texture(32, BLACK))]})[:-1])
assert "truncated" in refused(ko_light_maps.load, path, 17)
assert "whole 8-tile patches" in refused(ko_light_maps.load, path, 20)
print("PASS KO light maps (.tlt, 0059ba90 / 0059c450): blocks (2 px + tx, 2 pz + tz) with every A4R4G4B4 "
      "level as RGBA8; address 0, a negative address and a count of 0 read nothing, and no map gives no "
      "overlay; version, tx / tz outside 0..1, a block twice, a map not 32 x 32, a different mip chain, a "
      "block format, a record past the end and a truncated map refused")


# --- a package: cooker, client and server ---------------------------------------
atlas, vertices, built, hf, roof = fx.terrain()
w1 = fx.n3w1(atlas, vertices, [0, 1, 2])
lod = ko_lod.serialize(built)
WORK = B / "work"
package = fx.package(WORK, "terrain-overlay", w1, lod, heightfield=hf, triangles=roof, overlay=data)


def run(cmd, env=None):
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def check(pkg):
    client = run(["build/client/n3e-asset-check", str(pkg)])
    server = run(["target/debug/n3e-server", "--check-content"], env={**os.environ, "N3E_PACKAGE": str(pkg)})
    return client, server


client, server = check(package)
assert client.returncode == 0, client.stderr
assert "world overlay maps 3 side 32 levels 4 window 1 layers 36" in client.stdout.splitlines(), client.stdout
assert server.returncode == 0, server.stderr + server.stdout
# The release names it like any file, so it is part of the release identity.
assert "world-overlay.bin" in fx.records(package)[1]

# The cooker refuses a grid that does not cover the terrain policy's 4 patches.
narrow = world_overlay.serialize(dict(KO, width=4), {(0, 0): solid((0, 0, 0, 9))})
assert "differs from the terrain policy" in refused(fx.package, WORK, "narrow", w1, lod, heightfield=hf,
                                                   triangles=roof, overlay=narrow)
# The same, an overlay with trailing bytes, and a bad magic, installed into a
# cooked release past the cooker: the client refuses them; the server, which
# reads magic and size only, refuses the magic.
for name, bytes_, client_phrase, server_phrase in (
        ("narrow", narrow, "world overlay grid differs from the terrain policy", None),
        ("trailing", data + b"\0", "world overlay size", None),
        ("magic", b"N3WX" + data[4:], "world overlay magic", "world overlay magic")):
    copy = WORK / ("installed-" + name)
    shutil.rmtree(copy, ignore_errors=True)
    shutil.copytree(package, copy)
    fx.install(copy, "world-overlay.bin", bytes_)
    client, server = check(copy)
    assert client.returncode != 0 and client_phrase in client.stderr, (name, client.stderr)
    if server_phrase:
        assert server.returncode != 0 and server_phrase in server.stderr + server.stdout, (name, server.stderr)
    else:
        assert server.returncode == 0, (name, server.stderr + server.stdout)

# Without a world: the demo package with the overlay installed.
plain = WORK / "plain"
main.cook(Path("games/demo"), plain)
fx.install(plain, "world-overlay.bin", data)
client, server = check(plain)
assert client.returncode != 0 and "world overlay compatibility" in client.stderr, client.stderr
assert server.returncode != 0 and "world overlay compatibility" in server.stderr + server.stdout, server.stderr
source = WORK / "plain-source"
shutil.rmtree(source, ignore_errors=True)
shutil.copytree("games/demo", source)
m = json.loads((source / "package.json").read_text())
m["world_overlay"] = "overlay.bin"
(source / "package.json").write_text(json.dumps(m))
(source / "overlay.bin").write_bytes(data)
assert "requires a world and exploration" in refused(main.cook, source, WORK / "plain-cooked")
print("PASS N3WO package: cooked with a world, exploration and a covering grid, loaded by the client "
      "(3 maps, 36 window layers) and admitted by the server; a grid other than the terrain policy's, "
      "trailing bytes and a bad magic refused by the client (the magic by the server too); an overlay "
      "without a world refused by the cooker, the client and the server")
