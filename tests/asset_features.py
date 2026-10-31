"""Independent coverage beyond the retained two-bone Phase 0 fixture."""

import json, math, os, pathlib, shutil, struct, subprocess, sys, tempfile, zlib, binascii

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/assetc"))
import main as assetc
import gltf


def chunk(tag, b):
    return (
        struct.pack(">I", len(b))
        + tag
        + b
        + struct.pack(">I", binascii.crc32(tag + b) & 0xFFFFFFFF)
    )


# Build RGB texture rows encoded using all five PNG filters independently.
w, h = 7, 5
pixels = bytes((i * 37 + 19) % 256 for i in range(w * h * 3))
encoded = bytearray()
for y in range(h):
    mode = y
    encoded.append(mode)
    for x in range(w * 3):
        val = pixels[y * w * 3 + x]
        a = pixels[y * w * 3 + x - 3] if x >= 3 else 0
        b = pixels[(y - 1) * w * 3 + x] if y else 0
        c = pixels[(y - 1) * w * 3 + x - 3] if y and x >= 3 else 0
        p = a + b - c
        pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
        prediction = a if pa <= pb and pa <= pc else b if pb <= pc else c
        encoded.append((val - [0, a, b, (a + b) // 2, prediction][mode]) % 256)
png = (
    b"\x89PNG\r\n\x1a\n"
    + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    + chunk(b"IDAT", zlib.compress(encoded))
    + chunk(b"IEND", b"")
)
assert gltf.png(png) == (w, h, pixels)
for bad in [png[:-1], png + b"trailing", png[:30] + bytes([png[30] ^ 1]) + png[31:]]:
    try:
        gltf.png(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("bad PNG accepted")
print("PASS arbitrary RGB dimensions, all PNG filters and malformed lengths/CRC")
with tempfile.TemporaryDirectory() as td:
    root = pathlib.Path(td) / "source"
    out = pathlib.Path(td) / "out"
    shutil.copytree(ROOT / "tests/fixtures/legacy-demo", root)
    g = json.loads((root / "fixture.gltf").read_text())
    blob = bytearray((root / "fixture.bin").read_bytes())

    def accessor(rows, width):
        while len(blob) % 4:
            blob.append(0)
        off = len(blob)
        for row in rows:
            blob.extend(struct.pack("<" + "f" * width, *row))
        g["bufferViews"].append(
            {"buffer": 0, "byteOffset": off, "byteLength": len(blob) - off}
        )
        g["accessors"].append(
            {
                "bufferView": len(g["bufferViews"]) - 1,
                "componentType": 5126,
                "count": len(rows),
                "type": "VEC" + str(width),
            }
        )
        return len(g["accessors"]) - 1

    # X-axis root rotation, translated root, nonuniform animated tip scale,
    # and a vertex shared equally between root and tip bones.
    g["nodes"][0]["rotation"] = [math.sqrt(0.5), 0, 0, math.sqrt(0.5)]
    a = g["meshes"][0]["primitives"][0]["attributes"]
    ja = g["accessors"][a["JOINTS_0"]]
    wa = g["accessors"][a["WEIGHTS_0"]]
    struct.pack_into(
        "<4H",
        blob,
        g["bufferViews"][ja["bufferView"]]["byteOffset"] + 2 * 8,
        0,
        1,
        0,
        0,
    )
    struct.pack_into(
        "<4f",
        blob,
        g["bufferViews"][wa["bufferView"]]["byteOffset"] + 2 * 16,
        0.5,
        0.5,
        0,
        0,
    )
    anim = g["animations"][0]
    times = anim["samplers"][0]["input"]
    for node, path, values in [
        (0, "translation", [[0, 0, 0], [0.5, 0, 0], [1, 0, 0]]),
        (1, "scale", [[1, 1, 1], [1.5, 1, 1], [2, 1, 1]]),
    ]:
        output = accessor(values, 3)
        anim["channels"].append(
            {"sampler": len(anim["samplers"]), "target": {"node": node, "path": path}}
        )
        anim["samplers"].append(
            {"input": times, "output": output, "interpolation": "LINEAR"}
        )
    g["buffers"][0]["byteLength"] = len(blob)
    (root / "fixture.bin").write_bytes(blob)
    (root / "fixture.gltf").write_text(json.dumps(g))
    (root / "orientation.png").write_bytes(png)
    assetc.cook(root, out)
    result = subprocess.check_output(
        [str(ROOT / "build/client/n3e-asset-check"), str(out)], text=True
    ).splitlines()
    for line in result[1:6]:
        t, *v = map(float, line.split())
        angle = min(t, 1 - t) * math.pi / 3
        c, s = math.cos(angle), math.sin(angle)
        tipx = c * (1 + t) * 0.7 - s * 0.7
        tipy = 1 + s * (1 + t) * 0.7 + c * 0.7
        # Blend bones in model space, then rotate X by +90 degrees: (x,y,z)->(x,-z,y).
        expected = [(t + (0.7 + tipx) * 0.5) * 1.25, -0.21 * 0.8, (1.7 + tipy) * 0.5]
        assert max(abs(a - b) for a, b in zip(v[:3], expected)) < 1e-6, (t, v, expected)
    # Truncated but rehashed cooked collision must fail structural readers too.
    original = (out / "collision.bin").read_bytes()
    truncated = original[:-1]
    (out / "collision.bin").write_bytes(truncated)
    import hashlib

    index = bytearray((out / "release.bin").read_bytes())
    old = hashlib.sha256(original).digest()
    at = index.index(old)
    index[at : at + 32] = hashlib.sha256(truncated).digest()
    index[at - 4 : at] = struct.pack("<I", len(truncated))
    (out / "release.bin").write_bytes(index)
    for args, env in [
        ([str(ROOT / "build/client/n3e-asset-check"), str(out)], os.environ),
        (
            [str(ROOT / "target/debug/n3e-server"), "--check-content"],
            {**os.environ, "N3E_PACKAGE": str(out)},
        ),
    ]:
        assert subprocess.run(args, env=env, capture_output=True).returncode != 0
print(
    "PASS arbitrary-axis TRS, multiweight skinning, runtime tracks and rehashed malformed collision"
)


# ---------------------------------------------------------------------------
# Engine 12: the optional static world asset. It is the package's visible map
# geometry with its own atlas, separate from the instanced scene, so a map does
# not have to share a character's atlas or fit an animated scene's budget.
def world_asset(atlas=16, cell=8, pad=2, vertices=None, indices=None,
                magic=b"N3W1"):
    def u(n):
        return struct.pack("<I", n)

    pixels = bytes([200, 180, 160, 255]) * (atlas * atlas)
    # position, normal, two cell-local UV layers, and the slot each samples.
    vertices = vertices or [
        [0, 0, 0, 0, 1, 0, 0.25, 0.25, 0.5, 0.5, 1, 0],
        [4, 0, 0, 0, 1, 0, 2.75, 0.25, 0.5, 0.5, 1, 0],
        [0, 0, 4, 0, 1, 0, 0.25, 2.75, 0.5, 0.5, 1, 0],
    ]
    indices = [0, 1, 2] if indices is None else indices
    body = b"".join(struct.pack("<12f", *v) for v in vertices)
    return (magic + u(atlas) + u(atlas) + u(cell) + u(pad) + pixels
            + u(len(vertices)) + body
            + u(len(indices)) + b"".join(u(i) for i in indices))


def cook_world(td, asset=None, engine=12, world_key="map.n3world", drop_editing=False):
    root = pathlib.Path(td) / "world-source"
    out = pathlib.Path(td) / "world-cooked"
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(ROOT / "games/demo", root)
    manifest = json.loads((root / "package.json").read_text())
    if drop_editing:
        manifest.pop("editing")
    if world_key is not None:
        manifest["world"] = world_key
        (root / world_key).write_bytes(
            world_asset() if asset is None else asset)
    manifest["engine_version"] = engine
    (root / "package.json").write_text(json.dumps(manifest))
    assetc.cook(root, out)
    return out


with tempfile.TemporaryDirectory() as td:
    cooked = cook_world(td)
    assert (cooked / "world.bin").read_bytes()[:4] == b"N3W1"
    report = subprocess.check_output(
        [str(ROOT / "build/client/n3e-asset-check"), str(cooked)], text=True
    ).splitlines()
    assert report[0] == "world 16 16 3 1", report[0]
    # The server never interprets the asset but must still admit the release.
    assert subprocess.run(
        [str(ROOT / "target/debug/n3e-server"), "--check-content"],
        env={**os.environ, "N3E_PACKAGE": str(cooked)},
        capture_output=True,
    ).returncode == 0
    # Identity covers it: changing a pixel must change the release hash.
    before = (cooked / "release.sha256").read_text()
    changed = bytearray(world_asset())
    changed[24] ^= 0xFF
    assert (cook_world(td, bytes(changed)) / "release.sha256").read_text() != before
    cooked = cook_world(td)
    print("PASS engine 12 world asset: cooked, loaded, server-admitted, hashed into identity")

    for reason, kw in [
        ("wrong magic", dict(asset=world_asset(magic=b"N3S1"))),
        ("engine 11 with a world asset", dict(engine=11)),
        ("engine 12 without a world asset", dict(world_key=None)),
        ("world without the editing contract", dict(drop_editing=True)),
    ]:
        try:
            cook_world(td, **kw)
        except ValueError:
            continue
        raise AssertionError("cooker accepted " + reason)

    # Structural bounds are the client's, and they run before anything is drawn.
    for reason, asset in [
        ("index past the vertex count", world_asset(indices=[0, 1, 9])),
        ("triangle count not a multiple of three", world_asset(indices=[0, 1])),
        ("UV beyond the repeat bound", world_asset(vertices=[
            [0, 0, 0, 0, 1, 0, 0.25, 4096.0, 0.5, 0.5, 1, 0],
            [4, 0, 0, 0, 1, 0, 0.75, 0.25, 0.5, 0.5, 1, 0],
            [0, 0, 4, 0, 1, 0, 0.25, 0.75, 0.5, 0.5, 1, 0]])),
        ("atlas slot that does not exist", world_asset(vertices=[
            [0, 0, 0, 0, 1, 0, 0.25, 0.25, 0.5, 0.5, 4, 0],
            [4, 0, 0, 0, 1, 0, 0.75, 0.25, 0.5, 0.5, 1, 0],
            [0, 0, 4, 0, 1, 0, 0.25, 0.75, 0.5, 0.5, 1, 0]])),
        ("fractional atlas slot", world_asset(vertices=[
            [0, 0, 0, 0, 1, 0, 0.25, 0.25, 0.5, 0.5, 1.5, 0],
            [4, 0, 0, 0, 1, 0, 0.75, 0.25, 0.5, 0.5, 1, 0],
            [0, 0, 4, 0, 1, 0, 0.25, 0.75, 0.5, 0.5, 1, 0]])),
        ("zero normal", world_asset(vertices=[
            [0, 0, 0, 0, 0, 0, 0.25, 0.25, 0.5, 0.5, 1, 0],
            [4, 0, 0, 0, 1, 0, 0.75, 0.25, 0.5, 0.5, 1, 0],
            [0, 0, 4, 0, 1, 0, 0.25, 0.75, 0.5, 0.5, 1, 0]])),
        ("non power-of-two atlas", world_asset(atlas=24)),
        ("cell larger than the atlas", world_asset(cell=32)),
        ("border wider than a quarter cell", world_asset(pad=3)),
        ("trailing bytes", world_asset() + b"\x00"),
    ]:
        broken = cook_world(td, asset)
        done = subprocess.run(
            [str(ROOT / "build/client/n3e-asset-check"), str(broken)],
            capture_output=True)
        assert done.returncode != 0, "client accepted " + reason
    print("PASS world asset rejections: magic, engine pairing, editing prerequisite, "
          "indices, UV bound, atlas slots, normals, atlas grid, trailing bytes")
