"""N3W2 chunked world asset (PQ-231): writer, cooker, client and server agree.

The same original small world is cooked as N3W1 + N3L3 and as N3W2. Both load
in the client with the same totals and the same progressive topology, the server
admits both, and rehashed malformed N3W2 files and pairings are refused by the
client and the server. The 2048 m world and the captures are tests/world_chunks_live.py.

PQ-232: the client's chunk streamer, driven without GL (`n3e-asset-check
PACKAGE --stream ...`) along a camera path over a 1024 m world, keeps a bounded
resident set, evicts behind the camera and stops on a corrupt far chunk when it
is reached; a world of 4096 one-metre chunks stays at the 1024-chunk limit.

PQ-235: an N3W2 package cooks its collision as N3C2, and the target marker's
ground from that heightfield (`n3e-asset-check PACKAGE --marker ...`) equals the
all-resident terrain parts' along a path; N3C1 beside N3W2 is refused.

PQ-233: an N3W2 world's textures are an N3WT asset whose count the world's
header names. Client, server and cooker refuse it without N3W2 and N3W2
without it; the client, the writer and the cooker refuse malformed N3WT files
(counts, levels, sizes, truncation, more banks than the client binds).
"""
import copy
import json
import re
import os
import pathlib
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, "tests")
import world_chunk_fixture as fx  # noqa: E402
import world_chunks  # noqa: E402  (tools/assetc, on the path through the fixture)
import ko_lod  # noqa: E402
import main  # noqa: E402
import world_textures  # noqa: E402

ASSET, LOD, SERVER = "build/client/n3e-asset-check", "build/client/n3e-lod-check", "target/debug/n3e-server"


def client(package):
    return subprocess.run([ASSET, str(package)], capture_output=True, text=True)


def server(package):
    return subprocess.run([SERVER, "--check-content"], env={**os.environ, "N3E_PACKAGE": str(package)},
                          capture_output=True, text=True)


install = fx.install


def refused(package, why, by_server=True):
    c = client(package)
    assert c.returncode != 0, (why, c.stdout)
    if by_server:
        s = server(package)
        assert s.returncode != 0, (why, s.stdout)
    return c.stderr + (s.stderr if by_server else "")


w1, l3, w2 = fx.small_files()
with tempfile.TemporaryDirectory(dir="build") as td:
    one = fx.package(td, "n3w1", w1, l3)
    two = fx.package(td, "n3w2", w2)
    assert (two / "world.bin").read_bytes() == w2 and not (two / "world-lod.bin").exists()
    reports = []
    for package in (one, two):
        c = client(package)
        assert c.returncode == 0, c.stderr
        reports.append(c.stdout.splitlines())
        assert server(package).returncode == 0, server(package).stderr
    # 22 vertices and 140 triangles either way (4 x (2 + 32) terrain, 2 x 2 progressive).
    # N3W2 has no atlas (PQ-233): its textures are the N3WT asset's.
    assert reports[0][0] == "world 16 16 22 140" and reports[1][0] == "world 0 0 22 140", (reports[0][0], reports[1][0])
    assert reports[1][1] == "world chunks 4 parts 6", reports[1][1]
    assert reports[1][2] == "world textures 4 banks 3 pixels %d" % sum(len(p) for c in fx.textures() for _, _, p in c), reports[1][2]
    # Progressive topology over approach and retreat: the same multiset of
    # states (chunks reorder parts by grid cell, so lines are compared sorted).
    lod = [subprocess.run([LOD, str(p), "1"], capture_output=True, text=True, check=True).stdout.split("\n")
           for p in (one, two)]
    assert len(lod[0]) > 20 and sorted(lod[0]) == sorted(lod[1])
    print("PASS N3W1+N3L3 and N3W2 of one world: client totals, server admission and progressive topology agree")

    # The writer refuses what the reader would.
    a, vertices, built = fx.small()
    for change, why in [(lambda b: b.update(terrain_lod=None), "terrain part without a terrain policy"),
                        (lambda b: b["chunks"][4].update(parent=7), "world part parent"),
                        (lambda b: b["chunks"][0]["levels"][0][1].__setitem__(0, 99), "world index")]:
        b = {**built, "chunks": [dict(p, levels=[(d, list(ix)) for d, ix in p["levels"]]) for p in built["chunks"]]}
        change(b)
        try:
            world_chunks.serialize(fx.COUNT, vertices, b, (0, 0), 16, 2)
        except ValueError as e:
            assert why in str(e), (why, e)
        else:
            raise AssertionError(why)
    for grid, why in [(((0, 0), 16, 1), "outside the chunk grid"), (((0, 0), .5, 2), "grid bounds"),
                      (((0, 0), 16, 65), "grid bounds")]:
        try:
            world_chunks.serialize(fx.COUNT, vertices, built, *grid)
        except ValueError as e:
            assert why in str(e), (why, e)
        else:
            raise AssertionError(why)
    assert world_chunks.grid(built, 16) == (0.0, 0.0, 2)
    print("PASS N3W2 writer refuses dangling terrain, parents, indices and parts outside its grid")

    # Rehashed malformed files: the client refuses each; the server checks only
    # magic, size and pairing, so it is asked only about those.
    header = 4 + 4                                     # grid origin x
    table = header + 16 + 4 + 36 + 4                  # first chunk entry
    entry = 36

    def patched(offset, fmt, value, data=w2):
        out = bytearray(data)
        struct.pack_into(fmt, out, offset, value)
        return bytes(out)
    first_x, first_z = struct.unpack_from("<2I", w2, table)
    # The first body's terrain patch (0, 0): its kind, x and z after the table.
    kind2 = w2.index(struct.pack("<3I", 2, 0, 0), table + 4 * entry)
    malformed = {
        ("grid side 0", "cooked count"): patched(header + 12, "<I", 0),
        ("chunk size below 1 m", "world chunk grid"): patched(header + 8, "<f", .5),
        # PQ-232: a terrain patch's cell comes from the policy, so a shifted
        # grid already leaves patches without a chunk when the table is read.
        ("grid shifted off its parts", "terrain grid coverage"): patched(header, "<f", 40.0),
        ("terrain patch in another chunk", "world terrain patch cell"): patched(kind2 + 4, "<I", 1),
        ("chunk byte length", "world chunk table length"): patched(table + 32, "<I", struct.unpack_from("<I", w2, table + 32)[0] + 4),
        ("box not covering", "world chunk box cover"): patched(table + 8, "<f", struct.unpack_from("<f", w2, table + 8)[0] + 10),
        ("box inverted", "world chunk box"): patched(table + 20, "<f", -100.0),
        ("chunk order", "world chunk order"): patched(table + entry, "<I", first_x, patched(table + entry + 4, "<I", first_z)),
        ("cell beyond side", "cooked count"): patched(table, "<I", 2),
        ("terrain flag", "cooked count"): patched(header + 16, "<I", 2),
        ("truncated", "world chunk table length"): w2[:-1],
        ("trailing", "world chunk table length"): w2 + b"\0",
    }
    for (why, reason), data in malformed.items():
        install(two, "world.bin", data)
        c = client(two)
        assert c.returncode != 0 and reason in c.stderr, (why, c.stderr)
        assert server(two).returncode == 0, why  # magic, size and pairing are intact
    # A missing terrain patch: drop one terrain part through the writer.
    b = dict(built, chunks=built["chunks"][1:])
    install(two, "world.bin", world_chunks.serialize(fx.COUNT, vertices, b, (0, 0), 16, 2))
    assert "terrain grid coverage" in client(two).stderr
    print("PASS rehashed malformed N3W2 (grid, boxes, lengths, order, coverage, truncation) refused by the client")

    install(two, "world.bin", w2)
    assert client(two).returncode == 0
    install(two, "world-lod.bin", l3)
    assert "world/exploration compatibility" in refused(two, "N3W2 with world-lod.bin")
    install(two, "world-lod.bin", None)
    install(two, "world.bin", b"N3W9" + w2[4:])
    assert "world asset magic/size" in refused(two, "unknown world magic")
    install(two, "world.bin", w2)
    # N3W1 keeps its 32 MiB bound: the larger N3W2 bound is not a blanket raise.
    big = bytearray(w1)
    big += bytes(32 * 1024 * 1024 + 1 - len(big))
    install(one, "world.bin", bytes(big))
    assert "world asset magic/size" in refused(one, "N3W1 above 32 MiB")
    print("PASS client and server refuse N3W2 beside world-lod.bin, unknown world magic and an N3W1 over 32 MiB")

    # PQ-233: N3W2's textures are an N3WT asset. Pairing, magic and count
    # mismatches are refused by the client (and pairing and magic by the
    # server); malformed N3WT files by the client only (the server checks the
    # magic), with every reason the writer gives too.
    wt = fx.texture_bytes()
    assert (two / "world-textures.bin").read_bytes() == wt
    install(two, "world-textures.bin", None)
    assert "world textures compatibility" in refused(two, "N3W2 without world textures")
    install(two, "world-textures.bin", wt)
    install(one, "world.bin", w1)
    install(one, "world-textures.bin", wt)
    assert "world textures compatibility" in refused(one, "world textures beside N3W1")
    install(one, "world-textures.bin", None)
    install(two, "world-textures.bin", b"N3WX" + wt[4:])
    assert "world texture magic" in refused(two, "unknown world texture magic")

    def level_at(data, texture, level):
        """Offset of a texture level's width field."""
        at = 8
        for t in range(texture + 1):
            n = struct.unpack_from("<I", data, at)[0]
            at += 4
            for lv in range(n):
                if t == texture and lv == level:
                    return at
                w, h = struct.unpack_from("<2I", data, at)
                at += 8 + w * h * 4
        raise AssertionError("no such level")
    def raw(chains):
        """N3WT bytes without the writer's checks."""
        return b"N3WT" + struct.pack("<I", len(chains)) + b"".join(
            struct.pack("<I", len(c)) + b"".join(struct.pack("<2I", w, h) + px for w, h, px in c) for c in chains)
    five = fx.textures() + [fx.chain(4, (9, 9, 9, 255))]
    nine = [fx.chain(1 << k, (k, k, k, 255)) for k in range(9)]  # nine sizes: nine banks
    bad_textures = {
        ("count differs from the world", "world texture count"): world_textures.serialize(five),
        # The world's header is read first and names 4.
        ("texture count 0", "world texture count"): patched(4, "<I", 0, wt),
        ("texture count 4097", "world texture count"): patched(4, "<I", 4097, wt),
        ("level count 0", "cooked count"): patched(8, "<I", 0, wt),
        ("level count 13", "cooked count"): patched(8, "<I", 13, wt),
        ("non-power-of-two side", "world texture mip dimensions"): patched(12, "<I", 6, wt),
        ("level not half its parent", "world texture mip dimensions"): patched(level_at(wt, 0, 1), "<I", 8, wt),
        ("truncated", "truncated cooked data"): wt[:-1],
        ("trailing", "cooked trailing bytes"): wt + b"\0",
    }
    for (why, reason), data in bad_textures.items():
        install(two, "world-textures.bin", data)
        c = client(two)
        assert c.returncode != 0 and reason in c.stderr, (why, c.stderr)
        assert server(two).returncode == 0, why  # magic and pairing are intact
    # Nine sizes need nine banks, one more than the client binds: a world of
    # nine textures with them is refused.
    a, vertices, built = fx.small()
    w9 = world_chunks.serialize(9, vertices, built, (0, 0), 16, 2)
    install(two, "world.bin", w9)
    install(two, "world-textures.bin", raw(nine))
    c = client(two)
    assert c.returncode != 0 and "world texture bank bound" in c.stderr, c.stderr
    install(two, "world-textures.bin", raw(nine[:8] + nine[1:2]))
    c = client(two)
    assert c.returncode == 0 and "world textures 9 banks 8 " in c.stdout, c.stderr  # eight sizes, eight banks
    install(two, "world.bin", w2)
    install(two, "world-textures.bin", wt)
    assert client(two).returncode == 0
    for chains, why in [(nine, "world texture bank bound"), ([], "world texture count"),
                        ([fx.chain(8, (1, 1, 1, 1))[:1] + fx.chain(2, (1, 1, 1, 1))], "world texture mip dimensions")]:
        try:
            world_textures.serialize(chains)
        except ValueError as e:
            assert why in str(e), (why, e)
        else:
            raise AssertionError(why)
    try:
        world_chunks.serialize(3, vertices, built, (0, 0), 16, 2)  # slot 3 (clear) is out of range
    except ValueError as e:
        assert "world texture slot" in str(e), e
    else:
        raise AssertionError("slot beyond the texture count written")
    # The cooker: N3WT pairs with N3W2 only, and its count is the world's.
    for name, world, textures, why in (("n3w2-five", w2, world_textures.serialize(five), "world texture count differs"),
                                       ("n3w2-bad", w2, wt[:-1], "world texture truncated"),
                                       ("n3w2-nine", w9, raw(nine), "world texture bank bound")):
        try:
            fx.package(td, name, world, textures=textures)
        except ValueError as e:
            assert why in str(e), (why, e)
        else:
            raise AssertionError(why)
    root = pathlib.Path(td) / "n3w1-source"
    m = json.loads((root / "package.json").read_text())
    m["world_textures"] = "map.bin"
    (root / "package.json").write_text(json.dumps(m))
    try:
        main.cook(root, pathlib.Path(td) / "n3w1-textures")
    except ValueError as e:
        assert "world textures pair with an N3W2 world" in str(e), e
    else:
        raise AssertionError("world textures beside N3W1 cooked")
    print("PASS N3WT world textures: pairing, magic, count, level, size, truncation and bank bounds refused by "
          "client, writer and cooker; server checks pairing and magic")

    # The cooker: N3W2 pairs with exploration and names no LOD file.
    for name, lod in (("n3w2-with-lod", l3),):
        try:
            fx.package(td, name, w2, lod)
        except ValueError as e:
            assert "exploration vocabulary" in str(e), e
        else:
            raise AssertionError("N3W2 with a LOD file cooked")
    print("PASS cooker refuses an N3W2 world whose exploration policy names a LOD file")

    # PQ-232: streaming without GL. 1024 m of 64 m parts in 8 x 8 chunks of 128 m.
    def stream(package, path, reach):
        return subprocess.run([ASSET, str(package), "--stream", *map(str, path), str(reach)],
                              capture_output=True, text=True, timeout=300)

    def steps(out):
        return [dict((k, v) for k, v in (f.split("=") for f in line.split()[1:]))
                for line in out.splitlines() if line.startswith("WORLD_STREAM ")]
    a, vertices, built = fx.plain(16, 64, 5)
    medium = world_chunks.serialize(fx.COUNT, vertices, built, (0, 0), 128, 8)
    mid = fx.package(td, "stream", medium, fog_end=300)
    path = (64, 40, 64, 960, 40, 960, 32)
    r = stream(mid, path, 150)
    assert r.returncode == 0, r.stderr
    rows = steps(r.stdout)
    assert len(rows) == 33, r.stdout[-2000:]
    peak = re.search(r"^WORLD_STREAM_MAX resident=(\d+) bytes=(\d+) limits=1024 268435456 chunks=64$", r.stdout, re.M)
    resident = [int(x["resident"]) for x in rows]
    # reach 150 + margin 64 from a 128 m grid: a few chunks around the camera,
    # never the whole map, and the ones behind it leave as it moves.
    assert peak and 0 < max(resident) < 64 and int(peak.group(1)) < 64, (resident, peak)
    assert int(rows[-1]["evicted"]) > 0 and all(x["limited"] == "0" for x in rows), rows[-1]
    print("PASS N3W2 streamer: 1024 m path keeps %d-%d of 64 chunks resident (peak %s incl. in flight), "
          "evicts %s behind the camera" % (min(resident), max(resident), peak.group(1), rows[-1]["evicted"]))
    # The same path, with the far corner chunk (7, 7) corrupted and rehashed:
    # the start and the path up to it stream; reaching it stops the client.
    x, z, start, _ = fx.chunk_body(medium)[-1]
    assert (x, z) == (7, 7)
    bad = bytearray(medium)
    struct.pack_into("<I", bad, start, 0)  # vertex count 0: below the bound
    install(mid, "world.bin", bytes(bad))
    assert client(mid).returncode != 0  # the whole-world check sees it at once
    r = stream(mid, path, 150)
    rows = steps(r.stdout)
    assert r.returncode != 0 and "world chunk 7,7: cooked count" in r.stderr, (r.returncode, r.stderr)
    assert 16 <= len(rows) < 33, len(rows)  # streamed more than half the path first
    print("PASS N3W2 streamer: a corrupt chunk at the far corner fails closed when reached (step %d of 32): %s"
          % (len(rows), r.stderr.strip()))
    # A chunk larger than the stream byte limit could never be held: refused
    # at stream start as a bad package (review, PQ-232). Its body is padding;
    # the last table entry's length grows by 257 MiB.
    at = 4 + 4 + 16 + 4
    count = struct.unpack_from("<I", medium, at)[0]
    field = at + 4 + 36 * (count - 1) + 32
    huge = bytearray(medium)
    struct.pack_into("<I", huge, field, struct.unpack_from("<I", medium, field)[0] + (257 << 20))
    install(mid, "world.bin", bytes(huge) + bytes(257 << 20))
    del huge
    r = stream(mid, path, 150)
    assert r.returncode != 0 and "world chunk 7,7: larger than the stream byte limit" in r.stderr, r.stderr
    assert not steps(r.stdout), r.stdout[-500:]
    install(mid, "world.bin", medium)
    print("PASS N3W2 streamer: a chunk larger than the 256 MiB stream limit is refused at stream start")
    # 4096 one-metre chunks, all in reach: resident stops at the chunk limit.
    a, vertices, built = fx.plain(64, 1, 2)
    tiny = fx.package(td, "tiny", world_chunks.serialize(fx.COUNT, vertices, built, (0, 0), 1, 64), fog_end=300)
    r = stream(tiny, (32, 10, 32, 32, 10, 32, 1), 150)
    assert r.returncode == 0, r.stderr
    rows = steps(r.stdout)
    peak = re.search(r"^WORLD_STREAM_MAX resident=(\d+) .* chunks=4096$", r.stdout, re.M)
    assert rows[-1]["resident"] == "1024" and rows[-1]["limited"] == "3072" and rows[-1]["wanted"] == "4096", rows[-1]
    assert peak and int(peak.group(1)) == 1024, r.stdout[-500:]
    print("PASS N3W2 streamer: 4096 chunks in reach hold the 1024-chunk limit (nearest first, 3072 left out)")

# PQ-235: the target marker on an N3W2 world follows the package's native
# heightfield. The cooker writes N3C2 beside an N3W2 world whatever its size,
# and N3C1 beside the same world as N3W1 (byte for byte as before); along a
# path over the map and a roof object, the marker's ground parts from the
# heightfield equal those from the all-resident world's terrain parts, and an
# N3W2 package carrying an N3C1 collision is refused.
a, vertices, built, hf, roof = fx.terrain()
objects = [p for t in roof for p in t]
with tempfile.TemporaryDirectory(dir="build") as td:
    flat = fx.package(td, "terrain-n3w1", fx.n3w1(a, vertices, [0, 1, 2]), ko_lod.serialize(built),
                      heightfield=hf, triangles=roof)
    assert (flat / "collision.bin").read_bytes() == main.collision_bytes(hf, objects) \
        and (flat / "collision.bin").read_bytes()[:4] == b"N3C1"
    terrain = fx.package(td, "terrain", world_chunks.serialize(fx.COUNT, vertices, built, (-64, -64), 32, 4),
                         heightfield=hf, triangles=roof)
    collision = (terrain / "collision.bin").read_bytes()
    assert collision[:4] == b"N3C2" and collision == main.collision_bytes(hf, objects, native=True)
    assert client(terrain).returncode == 0 and server(terrain).returncode == 0, (client(terrain).stderr, server(terrain).stderr)
    STEPS = 400

    def marker(package):
        return subprocess.run([ASSET, str(package), "--marker", "-60", "-60", "60", "60", str(STEPS)],
                              capture_output=True, text=True)

    r = marker(terrain)
    assert r.returncode == 0, r.stderr
    row = dict(f.split("=", 1) for f in r.stdout.split()[1:])
    assert row["drawn"] == str(STEPS + 1) and int(row["vertices"]) == (STEPS + 1) * 6, row
    assert float(row["max_diff"]) <= 1e-4 and int(row["objects_above"]) > 0, row
    print("PASS N3W2 target marker ground: %s steps over a 128 m terrain world, %s ground vertices equal to the "
          "all-resident terrain parts (largest difference %s m), %s under the roof object left on the terrain"
          % (STEPS, row["vertices"], row["max_diff"], row["objects_above"]))
    install(terrain, "collision.bin", main.collision_bytes(hf, objects))
    r = marker(terrain)
    assert r.returncode != 0 and "needs an N3C2 terrain heightfield" in r.stderr, (r.returncode, r.stderr)
    print("PASS N3W2 target marker ground: an N3C1 collision beside an N3W2 world is refused")

# PQ-379 (D-201): N3W3 is N3W2 whose kind 0 and kind 1 parts may be alpha parts
# (flag bit 4) with their alpha record. One small world with an alpha
# progressive part, as N3W1 + N3L4 and as N3W3: the client reads the same
# record both ways and the server admits both; the writer keeps N3W2 without
# one; an N3W2 magic over alpha parts is refused by the client. A plain world
# (kind 0) with an alpha part loads too.
with tempfile.TemporaryDirectory(dir="build") as td:
    a, vertices, built = fx.small()
    record = dict(source=5, destination=6, state=0x101, point=[4, 5, 28])
    built["chunks"][4] = dict(built["chunks"][4], flags=8 | world_chunks.ALPHA, alpha=record)
    w3 = world_chunks.serialize(fx.COUNT, vertices, built, (0, 0), 16, 2)
    l4 = ko_lod.serialize(built)
    assert w3[:4] == b"N3W3" and l4[:4] == b"N3L4" and w2[:4] == b"N3W2" and l3[:4] == b"N3L3"
    lines = []
    for package in (fx.package(td, "n3l4", w1, l4), fx.package(td, "n3w3", w3)):
        c = client(package)
        assert c.returncode == 0 and server(package).returncode == 0, (c.stderr, server(package).stderr)
        lines.append([l for l in c.stdout.splitlines() if l.startswith("world alpha parts ")])
    assert lines[0] == lines[1] == ["world alpha parts 1 first 5 6 257 4 5 28"], lines
    old = fx.package(td, "n3w2-alpha", b"N3W2" + w3[4:])
    assert "world part bounds" in refused(old, "N3W2 magic over alpha parts", by_server=False)
    _, v, plain = fx.plain(2, 8.0, 3)
    plain["chunks"][1] = dict(plain["chunks"][1], flags=4 | world_chunks.ALPHA, alpha=dict(record, state=1))
    kind0 = fx.package(td, "n3w3-plain", world_chunks.serialize(fx.COUNT, v, plain, (0, 0), 8, 2))
    c = client(kind0)
    assert c.returncode == 0 and "world alpha parts 1 first 5 6 1 4 5 28" in c.stdout.splitlines(), c.stdout + c.stderr
    print("PASS N3W3 alpha parts (PQ-379, D-201): N3W1 + N3L4 and N3W3 carry the same record to the client, the "
          "server admits both, N3W2 is kept without one and refused over one, a kind 0 alpha part loads")

# PQ-382 (D-202): N3W4 is N3W3 whose parts that are not alpha parts may set bit
# 5 (cut at zero) and bit 6 (unlit). The same small world with its second
# progressive part carrying both, beside the alpha part, as N3W1 + N3L5
# and as N3W4: the client counts the same bits both ways and the server admits
# both; an N3W3 magic over them is refused; a kind 0 part with them loads.
with tempfile.TemporaryDirectory(dir="build") as td:
    a, vertices, built = fx.small()
    record = dict(source=5, destination=6, state=0x101, point=[4, 5, 28])
    built["chunks"][4] = dict(built["chunks"][4], flags=8 | world_chunks.ALPHA, alpha=record)
    assert built["chunks"][5]["kind"] == 1
    built["chunks"][5] = dict(built["chunks"][5], flags=8 | world_chunks.CUT_ZERO | world_chunks.UNLIT)
    w4 = world_chunks.serialize(fx.COUNT, vertices, built, (0, 0), 16, 2)
    l5 = ko_lod.serialize(built)
    assert w4[:4] == b"N3W4" and l5[:4] == b"N3L5"
    lines = []
    for package in (fx.package(td, "n3l5", w1, l5), fx.package(td, "n3w4", w4)):
        c = client(package)
        assert c.returncode == 0 and server(package).returncode == 0, (c.stderr, server(package).stderr)
        lines.append([l for l in c.stdout.splitlines() if l.startswith("world opaque parts ") or l.startswith("world alpha parts ")])
    assert lines[0] == lines[1] == ["world alpha parts 1 first 5 6 257 4 5 28",
                                    "world opaque parts cut-zero 1 unlit 1"], lines
    old = fx.package(td, "n3w3-opaque", b"N3W3" + w4[4:])
    assert "world part bounds" in refused(old, "N3W3 magic over the opaque bits", by_server=False)
    bad = dict(built, chunks=list(built["chunks"]))
    bad["chunks"][4] = dict(bad["chunks"][4], flags=bad["chunks"][4]["flags"] | world_chunks.UNLIT)
    try:
        world_chunks.serialize(fx.COUNT, vertices, bad, (0, 0), 16, 2)
    except ValueError:
        pass
    else:
        raise AssertionError("wrote an alpha part with the unlit bit")
    _, v, plain = fx.plain(2, 8.0, 3)
    plain["chunks"][1] = dict(plain["chunks"][1], flags=4 | world_chunks.CUT_ZERO | world_chunks.UNLIT)
    kind0 = fx.package(td, "n3w4-plain", world_chunks.serialize(fx.COUNT, v, plain, (0, 0), 8, 2))
    c = client(kind0)
    assert c.returncode == 0 and "world opaque parts cut-zero 1 unlit 1" in c.stdout.splitlines(), c.stdout + c.stderr
    print("PASS N3W4 opaque part bits (PQ-382, D-202): N3W1 + N3L5 and N3W4 carry the same bits to the client, "
          "the server admits both, N3W3 is refused over them, an alpha part with one is not written, a kind 0 "
          "part with them loads")

# PQ-388 (D-203): N3W5 is N3W4 whose vertices may set the second-layer slot to
# -1, a single-layer unlit vertex. The small world with its first terrain
# patch's four vertices marked is N3W5; the client loads it with the four marked
# vertices and the server admits it. Without a marked vertex the bytes stay
# N3W2. An N3W4 magic, or N3W1, over a marked vertex is refused; so are -1 in
# the first slot and any other negative slot, by the writer and by the client.
with tempfile.TemporaryDirectory(dir="build") as td:
    a, vertices, built = fx.small()
    assert world_chunks.serialize(fx.COUNT, vertices, built, (0, 0), 16, 2) == w2
    marked = [list(v) for v in vertices]
    for v in marked[:4]:
        v[11] = world_chunks.UNLIT_VERTEX
    w5 = world_chunks.serialize(fx.COUNT, marked, built, (0, 0), 16, 2)
    assert w5[:4] == b"N3W5" and w5[4:] != w2[4:] and len(w5) == len(w2)
    package = fx.package(td, "n3w5", w5)
    c = client(package)
    assert c.returncode == 0 and server(package).returncode == 0, (c.stderr, server(package).stderr)
    assert "world unlit vertices 4" in c.stdout.splitlines() and c.stdout.splitlines()[0] == "world 0 0 22 140", c.stdout
    old = fx.package(td, "n3w4-unlit", b"N3W4" + w5[4:])
    assert "world atlas slot" in refused(old, "N3W4 magic over an unlit vertex", by_server=False)
    flat = fx.package(td, "n3w1-unlit", fx.n3w1(a, marked, [0, 1, 2]), l3)
    assert "world atlas slot" in refused(flat, "N3W1 with an unlit vertex", by_server=False)
    minus_one, minus_two = struct.pack("<f", -1.0), struct.pack("<f", -2.0)
    assert w5.count(minus_one) == 4
    other = fx.package(td, "n3w5-minus-two", w5.replace(minus_one, minus_two))
    assert "world atlas slot" in refused(other, "slot -2", by_server=False)
    for bad_slot, column in ((-2.0, 11), (-1.0, 10)):
        bad = [list(v) for v in marked]
        bad[0][column] = bad_slot
        try:
            world_chunks.serialize(fx.COUNT, bad, built, (0, 0), 16, 2)
        except ValueError:
            pass
        else:
            raise AssertionError("wrote slot %g in column %d" % (bad_slot, column))
    print("PASS N3W5 single-layer unlit vertices (PQ-388, D-203): four marked vertices load and the server admits "
          "the world; unmarked it stays N3W2 byte for byte; N3W4 or N3W1 over a marked vertex, slot -2 and -1 in "
          "the first slot are refused")

# PQ-394 (D-212): N3W6 is N3W5 whose kind 0 and kind 1 parts may set bit 7, a
# texture sequence: u32 frame count, f32 fps, u32 slot per frame after the
# alpha record. The small world with its first progressive part cycling slots
# 1, 2, 0 at 10 fps and its second, an alpha part, cycling 2, 0 at 6.5 fps is
# N3W6; the client loads both records and the server admits it. Without the
# bit the bytes stay N3W2 / N3W3. An N3W5 magic over the bit, a frame count of
# 1, an fps of 0 and a slot at the texture count are refused by the client;
# the writer refuses those and more; no N3L file carries one; a kind 0 part
# with one loads.
with tempfile.TemporaryDirectory(dir="build") as td:
    a, vertices, built = fx.small()
    assert world_chunks.serialize(fx.COUNT, vertices, built, (0, 0), 16, 2) == w2
    first, second = built["chunks"][4], built["chunks"][5]
    assert first["kind"] == second["kind"] == 1
    assert {vertices[i][10] for i in range(first["base"], first["base"] + 3)} == {1.0}
    assert {vertices[i][10] for i in range(second["base"], second["base"] + 3)} == {2.0}
    alpha = dict(source=2, destination=1, state=0x41, point=[28, 5, 4])
    built["chunks"][4] = dict(first, flags=8 | world_chunks.SEQUENCE, sequence=dict(slots=[1, 2, 0], fps=10.0))
    built["chunks"][5] = dict(second, flags=8 | world_chunks.ALPHA | world_chunks.SEQUENCE, alpha=alpha,
                              sequence=dict(slots=[2, 0], fps=6.5))
    w6 = world_chunks.serialize(fx.COUNT, vertices, built, (0, 0), 16, 2)
    assert w6[:4] == b"N3W6", w6[:4]
    record = struct.pack("<If3I", 3, 10.0, 1, 2, 0)
    assert w6.count(record) == 1 and w6.count(struct.pack("<If2I", 2, 6.5, 2, 0)) == 1
    plain_alpha = dict(built, chunks=list(built["chunks"]))
    plain_alpha["chunks"][4] = dict(first)
    plain_alpha["chunks"][5] = dict(second, flags=8 | world_chunks.ALPHA, alpha=alpha)
    assert world_chunks.serialize(fx.COUNT, vertices, plain_alpha, (0, 0), 16, 2)[:4] == b"N3W3"
    package = fx.package(td, "n3w6", w6)
    c = client(package)
    assert c.returncode == 0 and server(package).returncode == 0, (c.stderr, server(package).stderr)
    # Chunk (1, 0), holding the alpha part at (28, 4), comes first.
    assert "world sequence parts 2 first 6.5 frames 2 0" in c.stdout.splitlines(), c.stdout
    assert "world alpha parts 1 first 2 1 65 28 5 4" in c.stdout.splitlines(), c.stdout
    old = fx.package(td, "n3w5-sequence", b"N3W5" + w6[4:])
    assert "world part bounds" in refused(old, "N3W5 magic over a sequence", by_server=False)
    for name, patched, why in (
            ("one-frame", struct.pack("<If3I", 1, 10.0, 1, 2, 0), "cooked count"),
            ("fps-zero", struct.pack("<If3I", 3, 0.0, 1, 2, 0), "world sequence part fps"),
            ("fps-high", struct.pack("<If3I", 3, 1001.0, 1, 2, 0), "world sequence part fps"),
            ("slot-count", struct.pack("<If3I", 3, 10.0, 1, 2, fx.COUNT), "world sequence part slot")):
        bad = fx.package(td, "n3w6-" + name, w6.replace(record, patched))
        stderr = refused(bad, name, by_server=False)
        assert why in stderr, (name, stderr)
    for name, change in (
            ("no record", lambda p: dict(p, sequence=None)),
            ("record without the bit", lambda p: dict(p, flags=8)),
            ("one frame", lambda p: dict(p, sequence=dict(slots=[1], fps=10.0))),
            ("65 frames", lambda p: dict(p, sequence=dict(slots=[1] * 65, fps=10.0))),
            ("fps 0", lambda p: dict(p, sequence=dict(slots=[1, 2], fps=0.0))),
            ("fps -1", lambda p: dict(p, sequence=dict(slots=[1, 2], fps=-1.0))),
            ("fps inf", lambda p: dict(p, sequence=dict(slots=[1, 2], fps=float("inf")))),
            ("fps 1001", lambda p: dict(p, sequence=dict(slots=[1, 2], fps=1001.0))),
            ("slot at the count", lambda p: dict(p, sequence=dict(slots=[1, fx.COUNT], fps=10.0))),
            ("vertices not on frame 0", lambda p: dict(p, sequence=dict(slots=[2, 1], fps=10.0)))):
        bad = dict(built, chunks=list(built["chunks"]))
        bad["chunks"][4] = change(built["chunks"][4])
        try:
            world_chunks.serialize(fx.COUNT, vertices, bad, (0, 0), 16, 2)
        except ValueError:
            pass
        else:
            raise AssertionError("wrote a sequence part with " + name)
    terrain = dict(built, chunks=list(built["chunks"]))
    terrain["chunks"][0] = dict(terrain["chunks"][0], flags=2 | world_chunks.SEQUENCE,
                                sequence=dict(slots=[0, 1], fps=10.0))
    for what, writer, world in (
            ("an N3W6 terrain patch", lambda b: world_chunks.serialize(fx.COUNT, vertices, b, (0, 0), 16, 2), terrain),
            ("an N3L part", ko_lod.serialize, built)):
        try:
            writer(world)
        except ValueError:
            pass
        else:
            raise AssertionError("wrote a sequence on " + what)
    _, v, plain = fx.plain(2, 8.0, 3)
    assert {v[i][10] for i in range(9)} == {0.0}
    plain["chunks"][0] = dict(plain["chunks"][0], flags=4 | world_chunks.SEQUENCE, sequence=dict(slots=[0, 1, 2, 1], fps=2.5))
    kind0 = fx.package(td, "n3w6-plain", world_chunks.serialize(fx.COUNT, v, plain, (0, 0), 8, 2))
    c = client(kind0)
    assert c.returncode == 0 and "world sequence parts 1 first 2.5 frames 0 1 2 1" in c.stdout.splitlines(), c.stdout + c.stderr
    print("PASS N3W6 texture sequences (PQ-394, D-212): two sequence records (one on an alpha part) load and the "
          "server admits the world; without the bit it stays N3W2 / N3W3; N3W5 over the bit, one frame, fps 0 or "
          "1001 and a slot at the texture count are refused by the client; the writer refuses bad records, a "
          "terrain patch's and vertices off frame 0; no N3L file carries one; a kind 0 sequence part loads")

# RQ-193: the writer refuses a world vertex exactly when the client's vertex
# reader would (read_world_vertices: twelve cooked floats, finite and within
# 1e6; the normal's single-precision length above 1e-10; UVs within 1024). An
# accepted row is written and loads; a refused one is forged into otherwise
# valid bytes (when it packs) to show the client refuses it too. The KO bake's
# own case (rotated normals, scaled positions) is tests/ko_terrain.py's.
def f32_step(x, step):
    bits = struct.unpack("<I", struct.pack("<f", x))[0] + step
    return struct.unpack("<f", struct.pack("<I", bits))[0]


edge = struct.unpack("<f", struct.pack("<f", 1e-10))[0]
above, at = (edge, f32_step(edge, -1)) if edge > 1e-10 else (f32_step(edge, 1), edge)
assert at <= 1e-10 < above
past = f32_step(1e6, 1)
nan, inf = float("nan"), float("inf")
VERTEX = 16  # the first progressive part's first vertex


def with_row(vertices, **columns):
    out = [list(v) for v in vertices]
    for name, value in columns.items():
        at_ = dict(p=0, n=3, uv=6)[name]
        out[VERTEX][at_:at_ + len(value)] = value
    return out


_, base_vertices, base_built = fx.small()
sentinel = with_row(base_vertices, n=[.6, 0, .8])
accepted = [dict(n=[0, above, 0]), dict(n=[1e6, 0, 0]), dict(n=[0, 0, -1e6]), dict(n=[above, above, above]),
            dict(n=[1e-10, 1e-10, 1e-10]), dict(p=[2, 1e6, 28]), dict(p=[2, -1e6, 28]),
            dict(uv=[1024, -1024, 1024, -1024])]
refused_rows = [dict(n=[0, 0, 0]), dict(n=[0, at, 0]), dict(n=[0, -at, 0]), dict(n=[1e-23, 1e-23, 1e-23]),
                dict(n=[nan, 0, 0]), dict(n=[0, inf, 0]), dict(n=[past, 0, 0]), dict(p=[2, past, 28]),
                dict(p=[-past, 4, 28]), dict(p=[2, 4, nan]), dict(p=[2, -inf, 28]),
                dict(uv=[f32_step(1024, 1), 0, 0, 0]), dict(uv=[0, 0, 0, -f32_step(1024, 1)])]
with tempfile.TemporaryDirectory(dir="build") as td:
    template = world_chunks.serialize(fx.COUNT, sentinel, base_built, (0, 0), 16, 2)
    row = struct.pack("<12f", *sentinel[VERTEX])
    assert template.count(row) == 1
    assert client(fx.package(td, "rq193-template", template)).returncode == 0
    for k, change in enumerate(accepted):
        v = with_row(sentinel, **change)
        world = world_chunks.serialize(fx.COUNT, v, base_built, (0, 0), 16, 2)
        assert world == template.replace(row, struct.pack("<12f", *v[VERTEX])), change
        c = client(fx.package(td, "rq193-accepted-%d" % k, world))
        assert c.returncode == 0, ("client refused a written vertex", change, c.stderr)
    for k, change in enumerate(refused_rows + [dict(p=[1e39, 4, 28]), dict(n=[0, -1e39, 0])]):
        v = with_row(sentinel, **change)
        for what, write in (("N3W2", lambda: world_chunks.serialize(fx.COUNT, v, base_built, (0, 0), 16, 2)),
                            ("row", lambda: world_chunks.vertex_row(v[VERTEX]))):
            try:
                write()
            except ValueError as e:
                assert str(e).startswith("world vertex "), e
            else:
                raise AssertionError(("wrote a vertex the client refuses", what, change))
    for k, change in enumerate(refused_rows):
        v = with_row(sentinel, **change)
        forged = fx.package(td, "rq193-refused-%d" % k, template.replace(row, struct.pack("<12f", *v[VERTEX])))
        why = "world UV" if "uv" in change else "zero normal" if "n" in change and all(
            x == x and abs(x) <= 1e6 for x in change["n"]) else "cooked finite bound"
        assert why in refused(forged, "forged vertex %r" % (change,), by_server=False), (change, why)
print("PASS world vertices (RQ-193): the writer refuses exactly the rows the client's vertex reader refuses "
      "(a float not finite or past 1e6, a normal whose single-precision length is at most 1e-10, a UV past "
      "1024); an accepted row is written and loads")

# RQ-194: the writers that packed world vertices by hand write them through
# world_chunks.vertex_row too: the Ashgrave N3W1 world (ashgrave.world_bytes)
# and the Demon's Souls level's vertex (demons_souls.world_vertex; the level
# itself needs the user's dump, so its vertex is tested on synthetic input).
# Each accepts RQ-193's accepted rows with the bytes packed as before and
# refuses its refused rows. The front-end's mesh vertices are not world
# vertices (8 floats, bounded by Reader::f alone): tests/front_end.py.
import ashgrave  # noqa: E402
import demons_souls  # noqa: E402

ash_grid = b"N3W1" + struct.pack("<4I", ashgrave.ATLAS, ashgrave.ATLAS, ashgrave.CELL, ashgrave.PAD)
ash_world, _ = ashgrave.build_world()
ash_rgba = bytes(4 * ashgrave.ATLAS * ashgrave.ATLAS)


def ash_bytes(vertices):
    w = ashgrave.World()
    w.vertices, w.indices = vertices, ash_world.indices
    return ashgrave.world_bytes(w, ash_rgba)


def ash_packed(vertices):
    return (ash_grid + ash_rgba + struct.pack("<I", len(vertices)) + b"".join(struct.pack("<12f", *v) for v in vertices)
            + struct.pack("<I", len(ash_world.indices)) + struct.pack("<%dI" % len(ash_world.indices), *ash_world.indices))


assert ash_bytes(ash_world.vertices) == ash_packed(ash_world.vertices)


def des_vertex(v):
    return demons_souls.world_vertex(v[0:3], v[3:6], v[6:8], v[10])


des_base = list(sentinel[VERTEX])
des_base[8:12] = [0.0, 0.0, 3.0, 0.0]  # the level's layout: one UV layer, its slot, slot 0 second
for change in [{}] + accepted:
    ash = with_row(ash_world.vertices, **change)
    assert ash_bytes(ash) == ash_packed(ash), change
    v = with_row([des_base] * (VERTEX + 1), **change)[VERTEX]
    v[8:10] = [0.0, 0.0]
    assert des_vertex(v) == struct.pack("<12f", *v), change
for change in refused_rows + [dict(p=[1e39, 4, 28]), dict(n=[0, -1e39, 0])]:
    v = with_row([des_base] * (VERTEX + 1), **change)[VERTEX]
    writers = [("ashgrave", lambda: ash_bytes(with_row(ash_world.vertices, **change)))]
    if not ("uv" in change and all(abs(x) <= 1024 for x in change["uv"][:2])):
        writers.append(("demons_souls", lambda: des_vertex(v)))  # its second layer is always 0
    for what, write in writers:
        try:
            write()
        except ValueError as e:
            assert str(e).startswith("world vertex "), (what, e)
        else:
            raise AssertionError(("wrote a vertex the client refuses", what, change))
print("PASS hand-packed world vertices (RQ-194): the Ashgrave world and the Demon's Souls level vertex write "
      "through vertex_row: the accepted rows as packed before, the refused ones refused")

# RQ-195: the chunked writer refuses a parent, a part head, a level distance or
# a control distance exactly as the client's reader does (the shared helpers
# world_chunks.parent_bytes, part_head and rising; tests/world_lod.py shows the
# N3L3 parity at each edge), and a grid origin or chunk box past the cooked
# float bound. Each field's offset is where two accepted values' bytes differ;
# an accepted value is written there and loads, a refused one is refused by
# the writer and, when it packs, forged there to show the client refuses it.
# The KO bake's own case (an OPD scale past 1000) is tests/ko_terrain.py's.
nan, inf = float("nan"), float("inf")
_, base_vertices, base_built = fx.small()
PART = 4  # the first progressive part (parent 0); part 0 is a terrain patch


def parent_field(k):
    return lambda b, v: b["parents"][0].__setitem__(k, v)


def scale_field(b, v):
    b["chunks"][PART]["scale"] = v


def level_field(j):
    return lambda b, v: b["chunks"][0]["levels"].__setitem__(j, (v, b["chunks"][0]["levels"][j][1]))


def control_field(j):
    def set_(b, v):
        controls = b["chunks"][PART]["progressive"]["controls"]
        controls[j] = (v, controls[j][1])
    return set_


radius_refused = [(f32_step(1e4, 1), "parent bounds"), (-1.0, "parent bounds"), (nan, "cooked finite bound"),
                  (1e39, None)]
rq195_cases = [
    ("parent distance radius", parent_field(3), [12.0, 0.0, 1e4], radius_refused),
    ("parent radius", parent_field(7), [8.0, -0.0, 1e4], radius_refused),
    ("part scale", scale_field, [1.0, 1000.0, 1e-30],
     [(0.0, "world part bounds"), (-0.0, "world part bounds"), (f32_step(1000.0, 1), "world part bounds"),
      (inf, "cooked finite bound")]),
    ("first level distance", level_field(0), [0.0, -0.0], [(1.0, "world LOD bounds"), (nan, "cooked finite bound")]),
    ("level distance", level_field(32), [32.0, 1e6], [(31.0, "world LOD bounds"), (past, "cooked finite bound")]),
    ("first control distance", control_field(0), [0.0, -0.5],
     [(-1.0, "progressive control"), (20.0, "progressive control")]),
    ("control distance", control_field(1), [20.0, 1e6], [(0.0, "progressive control"), (past, "cooked finite bound")]),
]


def rq195_write(set_, value):
    b = copy.deepcopy(base_built)
    set_(b, value)
    return world_chunks.serialize(fx.COUNT, base_vertices, b, (0, 0), 16, 2)


def rq195_refused(write, prefix):
    try:
        write()
    except ValueError as e:
        assert str(e).startswith(prefix), (prefix, e)
    else:
        raise AssertionError(("wrote a world the client refuses", prefix))


with tempfile.TemporaryDirectory(dir="build") as td:
    package = fx.package(td, "rq195", world_chunks.serialize(fx.COUNT, base_vertices, base_built, (0, 0), 16, 2))
    for name, set_, accepted, refused_values in rq195_cases:
        a, b = rq195_write(set_, accepted[0]), rq195_write(set_, accepted[1])
        assert len(a) == len(b) and a != b, name
        at = next(i for i in range(len(a)) if a[i] != b[i]) // 4 * 4
        assert a[:at] + a[at + 4:] == b[:at] + b[at + 4:], name
        for value in accepted:
            world = rq195_write(set_, value)
            assert world == a[:at] + struct.pack("<f", value) + a[at + 4:], (name, value)
            install(package, "world.bin", world)
            c = client(package)
            assert c.returncode == 0, ("client refused a written value", name, value, c.stderr)
        for value, why in refused_values:
            rq195_refused(lambda: rq195_write(set_, value), "world ")
            if why is not None:
                install(package, "world.bin", a[:at] + struct.pack("<f", value) + a[at + 4:])
                c = client(package)
                assert c.returncode != 0 and why in c.stderr, (name, value, why, c.stderr)
    # A part within its bounds can widen its chunk's box past the cooked float
    # bound: a 3 m triangle at x = 999990..999993 whose plain part is centred
    # at 999999 loads with radius 1 (its box reaches 1e6) and is refused at
    # radius 2 by the writer, whose box would reach past it.
    far = [[999990.0 + dx, 0.0, 8.0 + dz, 0, 1, 0, 0, 0, .5, .5, 1.0, float(fx.CLEAR)]
           for dx, dz in ((0, 0), (3, 0), (0, 3))]
    lone = dict(parents=[], terrain_lod=None, chunks=[dict(center=[999999.0, 0.0, 8.0], radius=1.0, scale=1.0,
                                                           flags=0, levels=[(0.0, [0, 2, 1])], kind=0)])
    origin = world_chunks.grid(lone, 16)
    assert origin == (999984.0, 0.0, 1), origin
    install(package, "world.bin", world_chunks.serialize(fx.COUNT, far, lone, origin[:2], 16, 1))
    c = client(package)
    assert c.returncode == 0, c.stderr
    lone["chunks"][0]["radius"] = 2.0
    rq195_refused(lambda: world_chunks.serialize(fx.COUNT, far, lone, origin[:2], 16, 1), "world chunk box ")
    rq195_refused(lambda: world_chunks.serialize(fx.COUNT, base_vertices, base_built, (-past, 0), 16, 2),
                  "world chunk grid ")
    for centre in ([past, 5, 28], [4, nan, 28], [4, 5, 1e39]):
        rq195_refused(lambda: rq195_write(lambda b, v: b["chunks"][PART].update(center=v), centre), "world part ")
    # A plain part's centre places it: past the float range it is outside any
    # grid (an error, not an overflow).
    for centre in ([inf, 5, 28], [4, 5, 1e39]):
        plain_part = lambda b, v: b["chunks"][PART].update(kind=0, center=v)
        rq195_refused(lambda: rq195_write(plain_part, centre), "world part ")
        b = copy.deepcopy(base_built)
        plain_part(b, centre)
        rq195_refused(lambda: world_chunks.grid(b, 16), "world part outside any chunk grid")
    for radius in (f32_step(2000.0, 1), -1.0, nan):
        rq195_refused(lambda: rq195_write(lambda b, v: b["chunks"][PART].update(radius=v), radius), "world part ")
print("PASS N3W2 world records (RQ-195): the writer refuses exactly the parents, part scales, level distances and "
      "control distances the client refuses, and part centres, radii, a grid origin or a chunk box past their "
      "bounds; an accepted value is written and loads")

# RQ-196: the chunked writer writes the terrain policy through the N3L
# writer's helper (world_chunks.policy_bytes; tests/world_lod.py shows the
# parity at each edge). Here the far factor and bias, which place nothing,
# are written and load at their edges; the origin, patch size and counts also
# place the patches, so their refused values are shown at the writer and, when
# they pack, forged into the written policy, where the client refuses them
# before it places a patch.


def policy_field(key, k=None):
    if k is None:
        return lambda b, v: b["terrain_lod"].__setitem__(key, v)
    return lambda b, v: b["terrain_lod"][key].__setitem__(k, v)


hundredth = struct.unpack("<f", struct.pack("<f", 0.01))[0]
rq196_cases = [
    ("far factor", policy_field("far_factor"), [1 / 1024, 1.0, 1e-30],
     [(0.0, "terrain detail policy"), (-0.0, "terrain detail policy"), (f32_step(1.0, 1), "terrain detail policy"),
      (nan, "cooked finite bound")]),
    ("bias", policy_field("bias"), [0.6, 0.0, f32_step(1.0, -1)],
     [(1.0, "terrain detail policy"), (-1e-30, "terrain detail policy"), (inf, "cooked finite bound"),
      (1e39, None)]),
]
with tempfile.TemporaryDirectory(dir="build") as td:
    package = fx.package(td, "rq196", world_chunks.serialize(fx.COUNT, base_vertices, base_built, (0, 0), 16, 2))
    good = rq195_write(lambda b, v: None, None)
    for name, set_, accepted, refused_values in rq196_cases:
        a, b = rq195_write(set_, accepted[0]), rq195_write(set_, accepted[1])
        assert len(a) == len(b) and a != b, name
        at = next(i for i in range(len(a)) if a[i] != b[i]) // 4 * 4
        assert a[:at] + a[at + 4:] == b[:at] + b[at + 4:] and a == good, name
        if name == "far factor":
            far_at = at
        for value in accepted:
            world = rq195_write(set_, value)
            assert world == a[:at] + struct.pack("<f", value) + a[at + 4:], (name, value)
            install(package, "world.bin", world)
            c = client(package)
            assert c.returncode == 0, ("client refused a written value", name, value, c.stderr)
        for value, why in refused_values:
            rq195_refused(lambda: rq195_write(set_, value), "terrain ")
            if why is not None:
                install(package, "world.bin", a[:at] + struct.pack("<f", value) + a[at + 4:])
                c = client(package)
                assert c.returncode != 0 and why in c.stderr, (name, value, why, c.stderr)
    # The origin and patch size sit before the far factor; the counts after the bias.
    terrain = base_built["terrain_lod"]
    assert good[far_at - 16:far_at + 20] == world_chunks.policy_bytes(terrain)
    forged = [("origin", far_at - 16, policy_field("origin", 0), [(past, "cooked finite bound"), (1e39, None)]),
              ("origin", far_at - 8, policy_field("origin", 2), [(nan, "cooked finite bound")]),
              ("patch size", far_at - 4, policy_field("patch_size"),
               [(f32_step(1000.0, 1), "terrain detail policy"), (f32_step(hundredth, -1), "terrain detail policy"),
                (0.0, "terrain detail policy"), (-1.0, "terrain detail policy")])]
    for name, at, set_, refused_values in forged:
        for value, why in refused_values:
            rq195_refused(lambda: rq195_write(set_, value), "terrain ")
            if why is not None:
                install(package, "world.bin", good[:at] + struct.pack("<f", value) + good[at + 4:])
                c = client(package)
                assert c.returncode != 0 and why in c.stderr, (name, value, why, c.stderr)
    for k, (key, top) in enumerate((("minimum", 64), ("band", 64), ("width", 256))):
        at = far_at + 8 + 4 * k
        assert good[at:at + 4] == struct.pack("<I", terrain[key]), key
        for n in (0, top + 1):
            rq195_refused(lambda: rq195_write(policy_field(key), n), "terrain policy %s outside" % key)
            install(package, "world.bin", good[:at] + struct.pack("<I", n) + good[at + 4:])
            c = client(package)
            assert c.returncode != 0 and "cooked count" in c.stderr, (key, n, c.stderr)
print("PASS N3W2 terrain policy (RQ-196): the writer refuses exactly the policies the client refuses (a float not "
      "finite or past 1e6, a patch size outside [0.01, 1000], a far factor outside (0, 1], a bias outside [0, 1)); "
      "the far factor and bias are written and load at their edges")
