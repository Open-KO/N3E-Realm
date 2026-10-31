"""Original synthetic KO bytes: decode, authority-independent conversion and bounds.
No real KO asset is used by make test.
"""

import copy
import json
import math
import pathlib
import struct
import subprocess
import sys
import tempfile
import hashlib
import zlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools/assetc"))
import ko_character as ko
import main as assetc
from common import string, f


def ints(*v):
    return struct.pack("<" + "i" * len(v), *v)


def transform(name):
    return string(name) + f([0, 0, 0, 0, 0, 0, 1, 1, 1, 1])


def expect_bad(fn):
    try:
        fn()
    except (ValueError, OSError, UnicodeError):
        return
    raise AssertionError("malformed input accepted")


# Analytic DXT1 colors; a three-colour block's index 3 is transparent black
# (alpha 0, PQ-265).
block = struct.pack("<HHI", 0xF800, 0x07E0, 0)
assert ko.dxt1(block, 4, 4) == bytes([255, 0, 0, 255]) * 16
assert (
    ko.dxt1(struct.pack("<HHI", 0xF800, 0x07E0, 0x55555555), 4, 4)
    == bytes([0, 255, 0, 255]) * 16
)
assert ko.dxt1(struct.pack("<HHI", 0, 1, 0xFFFFFFFF), 4, 4) == bytes(4) * 16
expect_bad(lambda: ko.dxt1(block[:-1], 4, 4))
# Independent reflected quarter-turn: X rotates to -Z in the converted basis.
q = ko.slerp([0, 0, 0, 1], [0, 1, 0, 0], 0.5)
m = ko.matrix([0, 0, 0], [-q[0], -q[1], q[2], q[3]])
assert abs(m[0][0]) < 1e-6 and abs(m[2][0] - 1) < 1e-6
assert (
    max(
        abs(v - float(i == j))
        for i, row in enumerate(ko.multiply(m, ko.inverse(m)))
        for j, v in enumerate(row)
    )
    < 1e-6
)
with tempfile.TemporaryDirectory() as td:
    root = pathlib.Path(td)
    material = f([1] * 4 + [0.5, 0.5, 0.5, 1] + [0] * 9) + struct.pack(
        "<6I", 4, 0, 2, 0, 5, 6
    )
    chrdata = (
        transform("original")
        + ints(0, 0, 0)
        + string("") * 2
        + string("Joint.bin")
        + ints(1)
        + string("Part.bin")
        + ints(0)
        + string("Anim.bin")
        + ints(-1, -1, -1, -1)
        + string("") * 2
    )
    joint = (
        transform("root")
        + ints(0)
        + ints(2, 1)
        + f([30])
        + f([0, 0, 0, 1, 0, 0, 1, 0])
        + ints(0, 0, 0)
    )
    animation = (
        ints(1, 0) + f([0, 1, 1, 0, 0, 0, 0, 0]) + ints(0) + f([0, 0]) + string("turn")
    )
    part = string("part") + ints(0) + material + string("Tex.bin") + string("Skin.bin")
    skin = (
        string("skins")
        + string("lod0")
        + ints(1, 3, 3)
        + f([0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 1])
        + struct.pack("<3H", 0, 1, 2)
        + f([0, 0, 1, 0, 0, 1])
        + struct.pack("<3H", 0, 1, 2)
    )
    for pos in ([0, 0, 0], [1, 0, 0], [0, 1, 0]):
        skin += f(pos) + ints(1, 0, 0, 0)
    skin += (string("empty") + ints(0, 0, 0)) * 3
    tex = string("tex") + b"NTF\x03" + ints(4, 4, 0x31545844, 1) + block
    files = {
        "Character.bin": chrdata,
        "Joint.bin": joint,
        "Anim.bin": animation,
        "Part.bin": part,
        "Skin.bin": skin,
        "Tex.bin": tex,
    }
    for name, data in files.items():
        (root / name).write_bytes(data)
    out = pathlib.Path("build/check/ko-original")
    report = ko.convert(root, "character.bin", out, 0, 1.0)
    cooked = out.parent / "ko-original-cooked"
    hash1 = assetc.cook(out, cooked)
    assert ko.convert(root, "CHARACTER.BIN", out, 0, 1.0)["render_vertices"] == 3
    assert assetc.cook(out, cooked) == hash1
    text = subprocess.check_output(
        ["build/client/n3e-asset-check", str(cooked)], text=True
    ).splitlines()
    first = list(map(float, text[1].split()))
    last = list(map(float, text[5].split()))
    # Output triangle reverses winding; the third output vertex is original X.
    assert max(abs(a - b) for a, b in zip(first[1:4], [1, 0, 0])) < 1e-6
    assert max(abs(a - b) for a, b in zip(last[1:4], [-1, 0, 0])) < 1e-6
    for parser, data in [
        (ko.character, chrdata),
        (ko.skeleton, joint),
        (ko.animations, animation),
        (ko.part, part),
        (ko.skins, skin),
        (ko.texture, tex),
    ]:
        expect_bad(lambda parser=parser, data=data: parser(data[:-1]))
        expect_bad(lambda parser=parser, data=data: parser(data + b"\0"))
    expect_bad(lambda: ko.Assets(root).get("../outside"))
    (root / "PART.BIN").write_bytes(part)
    expect_bad(lambda: ko.Assets(root).get("part.bin"))
print(
    "PASS original KO character/skin/DXT/animation fixtures, reflected pose, deterministic cooking, truncation/trailing/path ambiguity"
)


# PQ-264: parts whose UVs leave 0..1. KO samples character parts with wrap
# addressing (evidence/pq-264-ko-character-wrapping-uv.md), so the converter
# moves each such triangle by whole repeats and gives the part a repeated atlas
# region; a part inside 0..1 converts byte for byte as before.
# Outputs of the inside fixture under the converter before PQ-264.
UNCHANGED = "468b5c16d31d92238649d452262783639833f19c4801f74cada9da68e8e1a4ed"  # origin/main 5be8a16


def outputs(out):
    return hashlib.sha256(b"".join((out / n).read_bytes() for n in
                                   ("character.gltf", "character.bin", "atlas.png", "provenance.json"))).hexdigest()


def atlas_and_uv(out):
    g = json.loads((out / "character.gltf").read_text())
    data = (out / "character.bin").read_bytes()
    a = g["accessors"][g["meshes"][0]["primitives"][0]["attributes"]["TEXCOORD_0"]]
    view = g["bufferViews"][a["bufferView"]]
    uv = [struct.unpack_from("<2f", data, view["byteOffset"] + 8 * i) for i in range(a["count"])]
    png = (out / "atlas.png").read_bytes()
    width, height = struct.unpack(">II", png[16:24])
    at, idat = 8, b""
    while at < len(png):
        n, tag = struct.unpack(">I4s", png[at:at + 8])
        idat += png[at + 8:at + 8 + n] if tag == b"IDAT" else b""
        at += 12 + n
    raw = zlib.decompress(idat)
    rows = [raw[y * (width * 3 + 1) + 1:(y + 1) * (width * 3 + 1)] for y in range(height)]
    return uv, (lambda u, v: bytes(rows[int(v * height)][int(u * width) * 3:int(u * width) * 3 + 3]))


def texture8(tag):
    # 8 x 8 DXT1, four blocks with their own colours, every texel's index
    # varying with its column and row; NTF3's mip chains follow as zeros.
    blocks = b"".join(struct.pack("<HHI", c0, c1, sum(((x + 2 * y) % 4) << (2 * (y * 4 + x))
                                                     for y in range(4) for x in range(4)))
                      for c0, c1 in ((0xF800, 0x001F), (0x07E0, 0x0010), (0xFFE0, 0x0400), (0x8000, 0x07FF)))
    return string(tag) + b"NTF\x03" + ints(8, 8, 0x31545844, 1) + blocks + b"\0" * (8 + 32)


def wrap_skin(uvs):
    n = len(uvs)
    out = string("skins") + string("lod0") + ints(n // 3, n, n)
    out += b"".join(f([i * 0.1, (i % 3) * 0.1, 0, 0, 0, 1]) for i in range(n))
    out += struct.pack("<%dH" % n, *range(n)) + b"".join(f(list(uv)) for uv in uvs)
    out += struct.pack("<%dH" % n, *range(n))
    out += b"".join(f([i * 0.1, (i % 3) * 0.1, 0]) + ints(1, 0, 0, 0) for i in range(n))
    return out + (string("empty") + ints(0, 0, 0)) * 3


def wrap_files(root, uvs, texture_data=None):
    # Two parts: Part.bin inside 0..1 (the fixture above) and Wrap.bin.
    data = dict(files)
    data["Character.bin"] = chrdata.replace(ints(1) + string("Part.bin"),
                                            ints(2) + string("Part.bin") + string("Wrap.bin"))
    data["Wrap.bin"] = string("wrap") + ints(0) + material + string("Wrap8.bin") + string("WrapSkin.bin")
    data["Wrap8.bin"] = texture_data or texture8("wrap")
    data["WrapSkin.bin"] = wrap_skin(uvs)
    for name, value in data.items():
        (root / name).write_bytes(value)


def centre(i, k):
    return (i + 0.5) / 8 + k


with tempfile.TemporaryDirectory() as td:
    root = pathlib.Path(td)
    for name, data in files.items():
        (root / name).write_bytes(data)
    out = pathlib.Path("build/check/ko-wrap")
    ko.convert(root, "character.bin", out, 0, 1.0)
    assert outputs(out) == UNCHANGED, outputs(out)
    # Texel-centre corners: inside, below 0 (u -0.94), one triangle across
    # u = 1, one at v 1.06 to 1.81, one at u -2.94 to -2.69, one that stays
    # inside 0..1 in a wrapping part, and one just below u = 0 (-0.06).
    uvs = [(centre(0, 0), centre(0, 0)), (centre(3, 0), centre(1, 0)), (centre(1, 0), centre(4, 0)),
           (centre(0, -1), centre(2, 0)), (centre(2, -1), centre(2, 0)), (centre(1, -1), centre(5, 0)),
           (centre(6, 0), centre(3, 0)), (centre(0, 1), centre(3, 0)), (centre(7, 0), centre(6, 0)),
           (centre(2, 0), centre(0, 1)), (centre(5, 0), centre(6, 1)), (centre(3, 0), centre(2, 1)),
           (centre(0, -3), centre(1, 0)), (centre(2, -3), centre(7, 0)), (centre(1, -3), centre(4, 0)),
           (centre(4, 0), centre(4, 0)), (centre(6, 0), centre(5, 0)), (centre(5, 0), centre(7, 0)),
           (centre(7, -1), centre(0, 0)), (centre(1, 0), centre(1, 0)), (centre(2, 0), centre(0, 0))]
    source = ko.dxt1(texture8("wrap")[len(string("wrap")) + 20:len(string("wrap")) + 52], 8, 8)

    def wrapped_sample(u, v):
        x, y = int((u % 1) * 8), int((v % 1) * 8)
        return source[(y * 8 + x) * 4:(y * 8 + x) * 4 + 3]

    for player in (False, True):
        wrap_files(root, uvs)
        report = ko.convert(root, "character.bin", out, 0, 1.0, player=player)
        record = report["parts"][1]["wrapped_uv"]
        assert "wrapped_uv" not in report["parts"][0]
        # Triangles 1, 3 and 4 move by -1, +1 and -3 repeats; triangle 2
        # (across u = 1) keeps its place and widens the region to u 9 texels,
        # triangle 6 (u -0.06 to 0.31) keeps its place and widens it to u -1;
        # 0 and 5 stay inside.
        assert record["shifted_triangles"] == 3, record
        assert record["region_texels"] == [-1, 0, 9, 8], record
        coords, sample = atlas_and_uv(out)
        coords = coords[3:]  # after Part.bin's one triangle
        for t in range(0, len(uvs), 3):
            # Output corners are in source order; the winding is reversed
            # only in the index list.
            tri = list(zip(uvs[t:t + 3], coords[t:t + 3]))
            points = tri + [(tuple(sum(c[0][d] for c in tri) / 3 for d in (0, 1)),
                             tuple(sum(c[1][d] for c in tri) / 3 for d in (0, 1)))]
            for (u, v), (s, r) in points:
                assert sample(s, r) == wrapped_sample(u, v), (player, t, u, v, s, r)
    # Out of the 1024-texel atlas: a triangle across 129 repeats of an 8-texel
    # texture, and one across u 0.5 .. 2.5 of a 512-texel texture.
    wrap_files(root, [(0.0625, 0.0625), (128.9375, 0.0625), (0.0625, 0.5)])
    try:
        ko.convert(root, "character.bin", out, 0, 1.0)
    except ValueError as error:
        assert "past the 1024-texel atlas" in str(error), error
    else:
        raise AssertionError("oversized wrapping region accepted")
    big = string("big") + b"NTF\x03" + ints(512, 512, 0x31545844, 1) + struct.pack("<HHI", 0xF800, 0x001F, 0) * 128 * 128
    for factor in (0.5, 2):
        x = 256
        while x >= 4:
            big += bytes(int(x * x * factor))
            x //= 2
    wrap_files(root, [(0.5, 0.5), (2.5, 0.5), (1.5, 0.75)], big)
    try:
        ko.convert(root, "character.bin", out, 0, 1.0)
    except ValueError as error:
        assert "past the 1024-texel atlas" in str(error), error
    else:
        raise AssertionError("oversized wrapping region accepted")
print(
    "PASS wrapping part UVs (PQ-264): an inside part's outputs at their pin, moved triangles sample the "
    "wrapped texture at corners and centroids (gutter and no gutter), regions past the 1024-texel atlas refused"
)


# PQ-273: a clip that starts and ends on one frame is a held pose in KO (the
# clip start 0041be40 sets the frame to the start; the tick 00418b20 clamps it
# up to the start and, past the end, puts it back on the start; 00418e00 poses
# the joints at that frame; evidence/pq-273-ko-npc-zero-length-clips.md). It
# converts as two equal keys one 60 Hz sample apart; a clip that ends before
# it starts stays refused. The original fixture (clip 0) stays at its pin.
def clip(start, end, fps, strike):
    return ints(0) + f([start, end, fps, 0, 0, 0, 0, 0.25]) + ints(0) + f([strike, 0]) + string("c")


with tempfile.TemporaryDirectory() as td:
    root = pathlib.Path(td)
    for name, data in files.items():
        (root / name).write_bytes(data)
    out = pathlib.Path("build/check/ko-held")
    ko.convert(root, "character.bin", out, 0, 1.0)
    assert outputs(out) == UNCHANGED, outputs(out)
    # Clip 0 as before; 1 held on frame 0.5 (between the joint's two rotation
    # keys) with its strike there; 2 ends before it starts; 3 held on frame 0.
    (root / "Anim.bin").write_bytes(ints(4) + animation[4:-len(string("turn"))] + string("turn")
                                    + clip(0.5, 0.5, 30, 0.5) + clip(1, 0.5, 30, 0) + clip(0, 0, 30, 0))
    try:
        ko.convert(root, "character.bin", out, 2, 1.0)
    except ValueError as error:
        assert "clip ends before it starts" in str(error), error
    else:
        raise AssertionError("clip ending before it starts accepted")
    # The joint turns from identity to a half turn about z over frames 0 .. 1:
    # frame 0.5 is a quarter turn, frame 0 the identity (converted basis
    # (-x, -y, z, w)), independent of the converter's sampler.
    for index, angle in ((1, math.pi / 4), (3, 0.0)):
        for player in (False, True):
            report = ko.convert(root, "character.bin", out, index, 1.0, player=player)
            assert report["duration_seconds"] == 1 / 60 and report["held_frame"] == report["animations"][index]["start"]
            g = json.loads((out / "character.gltf").read_text())
            data = (out / "character.bin").read_bytes()

            def rows(accessor, width):
                a = g["accessors"][accessor]
                view = g["bufferViews"][a["bufferView"]]
                return [struct.unpack_from("<%df" % width, data, view["byteOffset"] + 4 * width * i)
                        for i in range(a["count"])]

            (sampler,) = g["animations"][0]["samplers"]
            assert [round(t[0], 7) for t in rows(sampler["input"], 1)] == [0, round(1 / 60, 7)]
            for q in rows(sampler["output"], 4):
                assert max(abs(a - b) for a, b in zip(q, [0, 0, math.sin(angle), math.cos(angle)])) < 1e-6, q
            meta = json.loads((out / "scene.json").read_text())
            assert meta["markers"] == ([{"name": "strike_0", "time": 0.0}] if index == 1 else []), meta["markers"]
            metadata = ko.animation_metadata(report)
            assert metadata["duration"] == 1 / 60 and metadata["markers"] == ([0.0, -1] if index == 1 else [-1, -1])
            # The client reader takes the cooked clip; every sampled time shows
            # the one held pose.
            cooked = out.parent / "ko-held-cooked"
            assetc.cook(out, cooked)
            text = subprocess.check_output(["build/client/n3e-asset-check", str(cooked)], text=True).splitlines()
            poses = [list(map(float, line.split()))[1:] for line in text[1:6]]
            assert all(max(abs(a - b) for a, b in zip(p, poses[0])) < 1e-6 for p in poses), poses
    # A clip with length keeps its outputs (no held_frame), as clip 0 above.
    assert "held_frame" not in ko.convert(root, "character.bin", out, 0, 1.0)
print(
    "PASS zero-length clips (PQ-273): a clip that starts and ends on one frame converts as that frame's pose held "
    "over two keys 1/60 s apart (gutter and no gutter, strike marker at 0, client reader), a clip ending before "
    "it starts refused, a clip with length at its pin"
)


# PQ-265 (D-173): part render states. KO's part renderer 00412570 acts on the
# material's flags 1 (blend with the material's factors), 4 (cull off) and
# 0x40 (lighting off; 2, fog off, is refused: not carried), and every part is
# alpha-tested against 0 (evidence/pq-265-ko-character-part-materials.md). A model with such a part
# or a texel below alpha 255 converts to one glTF primitive per run of parts
# sharing a state, an RGBA atlas, and cooks (looks clips only) to N3SM.
def material_bytes(flags=0, source=5, destination=6, diffuse=(1, 1, 1, 1)):
    return f(list(diffuse) + [0.5, 0.5, 0.5, 1] + [0] * 9) + struct.pack("<6I", 4, 0, 2, flags, source, destination)


def dxt3_texture(tag, alphas):
    # 4 x 4 DXT3: texel i has alpha alphas[i] (4 bits), colour c0 (index 0).
    alpha = sum(a << (4 * i) for i, a in enumerate(alphas))
    return string(tag) + b"NTF\x03" + ints(4, 4, 0x33545844, 1) + struct.pack("<QHHI", alpha, 0x001F, 0x0000, 0)


def scene_runs(scene):
    """(magic, runs) of a cooked N3S1/N3SM scene.bin, read independently."""
    at = 4
    width, height = struct.unpack_from("<II", scene, at)
    at += 8 + width * height * (4 if scene[:4] == b"N3SM" else 3)
    nodes = struct.unpack_from("<I", scene, at)[0]
    at += 4 + nodes * 44
    joints = struct.unpack_from("<I", scene, at)[0]
    at += 4 + joints * 68
    tracks = struct.unpack_from("<I", scene, at)[0]
    at += 4
    for _ in range(tracks):
        keys = struct.unpack_from("<I", scene, at + 8)[0]
        at += 12 + keys * 20
    vertices = struct.unpack_from("<I", scene, at)[0]
    at += 4 + vertices * 64
    indices = struct.unpack_from("<I", scene, at)[0]
    at += 4 + indices * 4
    runs = []
    if scene[:4] == b"N3SM":
        for i in range(struct.unpack_from("<I", scene, at)[0]):
            first, n, flags, reference, src, dst = struct.unpack_from("<IIIfII", scene, at + 4 + 24 * i)
            runs.append((first, n, flags, reference, src, dst))
        at += 4 + 24 * len(runs)
    assert at + 16 == len(scene), (at, len(scene))
    return scene[:4], runs


def atlas_rgba(out):
    png = (out / "atlas.png").read_bytes()
    width, height, depth, color = struct.unpack(">IIBB", png[16:26])
    at, idat = 8, b""
    while at < len(png):
        n, tag = struct.unpack(">I4s", png[at:at + 8])
        idat += png[at + 8:at + 8 + n] if tag == b"IDAT" else b""
        at += 12 + n
    channels = {2: 3, 6: 4}[color]
    raw = zlib.decompress(idat)
    return width, height, channels, [raw[y * (width * channels + 1) + 1:(y + 1) * (width * channels + 1)]
                                     for y in range(height)]


# Analytic DXT3: per-texel 4-bit alpha, low nibble first, times 17; colour
# from a four-colour block even when c0 <= c1.
decoded = ko.dxt3(struct.pack("<QHHI", sum((i % 16) << (4 * i) for i in range(16)), 0x001F, 0xF800, 0), 4, 4)
assert [decoded[4 * i + 3] for i in range(16)] == [17 * i for i in range(16)], decoded
assert decoded[:3] == bytes([0, 0, 255]), decoded[:4]
assert ko.texture(dxt3_texture("t", [15] * 16))[2] == bytes([0, 0, 255, 255]) * 16
expect_bad(lambda: ko.texture(dxt3_texture("t", [15] * 16)[:-1]))
expect_bad(lambda: ko.texture(dxt3_texture("t", [15] * 16) + b"\0"))
# A DXT1 whose c0 <= c1 with every index 3: transparent black.
see_through = string("w") + b"NTF\x03" + ints(4, 4, 0x31545844, 1) + struct.pack("<HHI", 0x0010, 0x07E0, 0xFFFF00FF)

with tempfile.TemporaryDirectory() as td:
    root = pathlib.Path(td)

    def build(parts):
        """Writes the original fixture with `parts`: (name, material, texture)."""
        data = dict(files)
        data["Character.bin"] = chrdata.replace(ints(1) + string("Part.bin"),
                                                ints(len(parts)) + b"".join(string(n) for n, _, _ in parts))
        for name, mat, texture_data in parts:
            if name == "Part.bin":
                continue  # the original fixture's part
            data[name] = string(name) + ints(0) + mat + string(name + ".dxt") + string("Skin.bin")
            data[name + ".dxt"] = texture_data
        for name, value in data.items():
            (root / name).write_bytes(value)

    out = pathlib.Path("build/check/ko-materials")
    cooked = out.parent / "ko-materials-cooked"
    # The original opaque fixture keeps its pin (one primitive, RGB atlas, no
    # render state recorded), and so does an opaque part with a DXT3 texture
    # whose texels are all alpha 15.
    build([("Part.bin", material, tex)])
    ko.convert(root, "character.bin", out, 0, 1.0)
    assert outputs(out) == UNCHANGED, outputs(out)
    build([("Part.bin", material, tex), ("Solid.bin", material, dxt3_texture("s", [15] * 16))])
    report = ko.convert(root, "character.bin", out, 0, 1.0)
    g = json.loads((out / "character.gltf").read_text())
    assert len(g["meshes"][0]["primitives"]) == 1 and "extensionsUsed" not in g and atlas_rgba(out)[2] == 3
    assert all("render_state" not in p for p in report["parts"])
    # Opaque, double-sided with a see-through DXT1, then blend + unlit on DXT3,
    # then a second blend + unlit part (one run with the third).
    states = [ko.OPAQUE_STATE, dict(ko.OPAQUE_STATE, double_sided=True),
              dict(ko.OPAQUE_STATE, blend=["src_alpha", "one_minus_src_alpha"], lit=False)]
    build([("Part.bin", material, tex), ("Wing.bin", material_bytes(4), see_through),
           ("Glow.bin", material_bytes(0x41), dxt3_texture("g", [i % 16 for i in range(16)])),
           ("Glow2.bin", material_bytes(0x41), dxt3_texture("h", [8] * 16))])
    for player in (False, True):
        try:
            report = ko.convert(root, "character.bin", out, 0, 1.0, player=player)
        except ValueError as error:
            assert player and "NPC looks only" in str(error), error
            continue
        assert not player
    g = json.loads((out / "character.gltf").read_text())
    primitives = g["meshes"][0]["primitives"]
    assert g["extensionsUsed"] == ["N3E_render_state"] and len(primitives) == 3, g["meshes"]
    assert [g["materials"][p["material"]]["extensions"]["N3E_render_state"] for p in primitives] == states
    assert [g["accessors"][p["indices"]]["count"] for p in primitives] == [3, 3, 6]
    assert [p["render_state"] for p in report["parts"]] == [states[0], states[1], states[2], states[2]]
    # The atlas keeps each texture's alpha: the wing's texels 0, the glow's
    # nibbles times 17, the opaque parts 255.
    width, height, channels, rows = atlas_rgba(out)
    assert channels == 4
    alphas = sorted({row[4 * x + 3] for row in rows for x in range(width)})
    assert {0, 255, 8 * 17} <= set(alphas) and set(17 * i for i in range(16)) <= set(alphas), alphas
    # Cooked as a looks clip: N3SM with the three runs in part order; any
    # other cook refuses the render states.
    assetc.cook(out, cooked, materials=True)
    magic, runs = scene_runs((cooked / "scene.bin").read_bytes())
    assert magic == b"N3SM" and runs == [(0, 3, 0, 0.0, 0, 0), (3, 3, 2, 0.0, 0, 0), (6, 6, 5, 0.0, 4, 5)], runs
    expect_bad(lambda: assetc.cook(out, out.parent / "ko-materials-refused"))
    # A mesh with a see-through texel and no flag is N3SM with one opaque,
    # alpha-tested run.
    build([("Part.bin", material, tex), ("Cut.bin", material, see_through)])
    ko.convert(root, "character.bin", out, 0, 1.0)
    assetc.cook(out, cooked, materials=True)
    assert scene_runs((cooked / "scene.bin").read_bytes()) == (b"N3SM", [(0, 6, 0, 0.0, 0, 0)])
    # Fail closed: flags 00412570 does not test (8, 0x80, 0x100) or whose
    # draw n3e lacks (0x800), a diffuse other than white, blend factors past
    # D3DBLEND 10 under flag 1. Factors are ignored without flag 1.
    for mat, why in [(material_bytes(8), "render flags 0x8"), (material_bytes(0x800), "render flags 0x800"),
                     (material_bytes(2), "render flags 0x2"), (material_bytes(0x43), "render flags 0x2"),
                     (material_bytes(0x180), "render flags 0x180"),
                     (material_bytes(0, diffuse=(1, 1, 1, 0.5)), "diffuse"),
                     (material_bytes(0, diffuse=(0.5, 1, 1, 1)), "diffuse"),
                     (material_bytes(1, 11, 6), "blend factors 11/6"), (material_bytes(1, 5, 0), "blend factors 5/0")]:
        build([("Part.bin", material, tex), ("Bad.bin", mat, tex)])
        try:
            ko.convert(root, "character.bin", out, 0, 1.0)
        except ValueError as error:
            assert why in str(error), (why, error)
        else:
            raise AssertionError("material accepted: " + why)
    assert ko.render_state([1, 1, 1, 1] + [0] * 13 + [4, 0, 2, 0, 11, 0]) == ko.OPAQUE_STATE
    # The glTF cooker's own bounds on render states (looks clips only).
    build([("Part.bin", material, tex), ("Wing.bin", material_bytes(4), see_through)])
    ko.convert(root, "character.bin", out, 0, 1.0)
    good = (out / "character.gltf").read_text()

    def bad_gltf(change):
        g = json.loads(good)
        change(g)
        (out / "character.gltf").write_text(json.dumps(g))
        expect_bad(lambda: assetc.cook(out, out.parent / "ko-materials-refused", materials=True))
        (out / "character.gltf").write_text(good)

    state = lambda g, i=1: g["materials"][i]["extensions"]["N3E_render_state"]  # noqa: E731
    bad_gltf(lambda g: g["materials"][0].pop("extensions"))  # a primitive without a state
    bad_gltf(lambda g: state(g).update(alpha_reference=1.0))
    bad_gltf(lambda g: state(g).update(blend=["src_alpha", "inverse"]))
    bad_gltf(lambda g: state(g).update(extra=True))
    bad_gltf(lambda g: state(g).update(lit=1))
    bad_gltf(lambda g: state(g).update(fog=False))  # no fog state is carried (flag 2 refused)
    bad_gltf(lambda g: g.update(extensionsUsed=["KHR_materials_unlit"]))
    bad_gltf(lambda g: g["meshes"][0]["primitives"].extend([g["meshes"][0]["primitives"][0]] * 15))  # 17 runs
    bad_gltf(lambda g: g["meshes"][0]["primitives"][1].update(attributes=dict(g["meshes"][0]["primitives"][1]["attributes"], NORMAL=0)))
    assetc.cook(out, cooked, materials=True)
print(
    "PASS part render states (PQ-265): DXT3 and see-through DXT1 alpha, the opaque fixture at its pin, one glTF "
    "primitive per run of parts sharing a state, RGBA atlas, N3SM runs in part order (looks clips only; other cooks "
    "and the player path refuse), refused flags/diffuse/blend factors, the cooker's render-state bounds"
)


# PQ-266: joint scale. KO's joint matrix 00427a50 is rotation(q) x scale(s) in
# row vectors (rotate, then scale along the parent's axes; 0041dda0 is
# this = this x argument), the position put into row 3 after, times the
# parent's matrix; the ticks 0043b710 and 00427640 replace the scale from a
# scale track by linear interpolation (evidence/pq-266-ko-character-joint-scale.md).
# The reference below is that arithmetic in KO's row-vector form, written out
# from the decompiled functions, not the converter's: the client's skinned
# vertices (n3e-asset-check, through the cooked N3S1) must match it at every
# printed time, and the other order (scale before rotation) must not.
def key_bytes(kind, rate, values):
    if not values:
        return ints(0)
    return ints(len(values), kind) + f([rate]) + b"".join(f(v) for v in values)


def joint_bytes(name, p, q, s, keys=(None, None, None), children=()):
    out = string(name) + f(p + q + s)
    for kind, k in zip((0, 1, 0), keys):
        out += key_bytes(kind, *(k or (30, [])))
    out += ints(0) + ints(len(children))  # no orientation track
    return out + b"".join(children)


def ko_rotation(q):
    # 0064cad6 (row-major, row vectors).
    x, y, z, w = q
    return [[1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w), 0],
            [2 * (x * y - z * w), 1 - 2 * (x * x + z * z), 2 * (y * z + x * w), 0],
            [2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y), 0],
            [0, 0, 0, 1]]


def row_multiply(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def ko_key(k, frame, default, rotation=False):
    # 00427640 / 0043b710: index trunc(frame x rate / 30), then lerp or slerp.
    if not k:
        return default
    rate, values = k
    span = 30 / rate
    i = int(frame / span)
    if i >= len(values) - 1:
        return values[-1]
    t = (frame - i * span) / span
    a, b = values[i], values[i + 1]
    if not rotation:
        return [x * (1 - t) + y * t for x, y in zip(a, b)]
    d = sum(x * y for x, y in zip(a, b))
    angle = math.acos(min(1, d))
    return [(x * math.sin((1 - t) * angle) + y * math.sin(t * angle)) / math.sin(angle) for x, y in zip(a, b)]


def ko_worlds(tree, frame, scale_first=False):
    worlds = []
    for name, parent, p, q, s, keys in tree:
        p = ko_key(keys[0], frame, p)
        q = ko_key(keys[1], frame, q, True)
        s = ko_key(keys[2], frame, s)
        scale = [[s[0], 0, 0, 0], [0, s[1], 0, 0], [0, 0, s[2], 0], [0, 0, 0, 1]]
        m = row_multiply(scale, ko_rotation(q)) if scale_first else row_multiply(ko_rotation(q), scale)
        m[3] = p + [1]
        worlds.append(row_multiply(m, worlds[parent]) if parent >= 0 else m)
    return worlds


def ko_skinned(tree, frame, origin, influences, scale_first=False):
    bind, now = ko_worlds(tree, 0, scale_first), ko_worlds(tree, frame, scale_first)
    out = [0, 0, 0]
    for joint, weight in influences:
        m = row_multiply(ko.inverse(bind[joint]), now[joint])
        for c in range(3):
            out[c] += weight * (sum(origin[r] * m[r][c] for r in range(3)) + m[3][c])
    return [out[0], out[1], -out[2]]  # n3e's mirror


half = math.sqrt(0.5)
# root (unscaled, static); arm (scale 1, 2, 0.5 and a turn about z from 0 to
# 90 degrees over the clip); hand (static scale (1, 1, 1) is replaced by a
# scale track from 1, 1, 1 to 3, 1, 0.5, a fixed tilt about x, a translation
# track).
tree = [
    ("root", -1, [0, 0, 0], [0, 0, 0, 1], [1, 1, 1], (None, None, None)),
    ("arm", 0, [1, 0, 0], [0, 0, 0, 1], [1, 2, 0.5],
     (None, (1, [[0, 0, 0, 1], [0, 0, half, half]]), None)),
    ("hand", 1, [0, 1, 0], [math.sin(0.3), 0, 0, math.cos(0.3)], [1, 1, 1],
     ((1, [[0, 1, 0], [0.5, 1, 0]]), None, (1, [[1, 1, 1], [3, 1, 0.5]]))),
]
scaled_joint = joint_bytes("root", *tree[0][2:5], children=[
    joint_bytes("arm", *tree[1][2:5], keys=tree[1][5], children=[joint_bytes("hand", *tree[2][2:5], keys=tree[2][5])])])
# Corner 1 (printed vertex 2) on the arm, corner 6 (printed vertex 6) half on
# the arm and half on the hand; the rest on the root.
corners = [([0.2, 0.1, 0.0], [(0, 1.0)]), ([1.5, 0.4, 0.3], [(1, 1.0)]), ([0.1, 0.3, 0.0], [(0, 1.0)]),
           ([0.0, 0.0, 0.2], [(0, 1.0)]), ([0.3, 0.0, 0.1], [(0, 1.0)]), ([0.0, 0.2, 0.3], [(0, 1.0)]),
           ([1.2, 1.4, -0.4], [(1, 0.5), (2, 0.5)]), ([0.1, 0.1, 0.1], [(0, 1.0)]), ([0.2, 0.0, 0.3], [(0, 1.0)])]


def scaled_skin(points):
    n = len(points)
    out = string("skins") + string("lod0") + ints(n // 3, n, n)
    out += b"".join(f(p + [0, 0, 1]) for p, _ in points) + struct.pack("<%dH" % n, *range(n))
    out += b"".join(f([0.1, 0.1]) for _ in points) + struct.pack("<%dH" % n, *range(n))
    for p, influences in points:
        out += f(p) + ints(len(influences)) + bytes(8) + ints(*[j for j, _ in influences])
        if len(influences) > 1:
            out += f([w for _, w in influences])
    return out + (string("empty") + ints(0, 0, 0)) * 3


with tempfile.TemporaryDirectory() as td:
    root = pathlib.Path(td)
    for name, data in files.items():
        (root / name).write_bytes(data)
    out = pathlib.Path("build/check/ko-scale")
    cooked = out.parent / "ko-scale-cooked"
    ko.convert(root, "character.bin", out, 0, 1.0)
    assert outputs(out) == UNCHANGED, outputs(out)  # no scaled joint: as before
    (root / "Joint.bin").write_bytes(scaled_joint)
    (root / "Skin.bin").write_bytes(scaled_skin(corners))
    (root / "Anim.bin").write_bytes(ints(1, 0) + f([0, 30, 30, 0, 0, 0, 0, 0]) + ints(0) + f([0, 0]) + string("arm"))
    # The bounds readers (nameplates, render detail, target marker) build
    # unscaled world matrices: their skeleton read keeps refusing a scale.
    try:
        ko.skeleton(scaled_joint)
    except ValueError as error:
        assert "scaled KO joint unsupported" in str(error), error
    else:
        raise AssertionError("scaled skeleton accepted by the unscaled reader")
    assert [b["name"] for b in ko.skeleton(scaled_joint, scaled=True)] == ["root", "arm", "hand"]
    for player in (False, True):
        report = ko.convert(root, "character.bin", out, 0, 1.0, player=player)
        assert report["scaled_joints"] == [{"joint": 1, "name": "arm", "scale_node": 4},
                                           {"joint": 2, "name": "hand", "scale_node": 5}], report["scaled_joints"]
        g = json.loads((out / "character.gltf").read_text())
        nodes = g["nodes"]
        # Joints keep their indices (0-2), the mesh node is 3, the scale
        # nodes follow: root -> arm scale (4) -> arm -> hand scale (5) -> hand.
        assert g["skins"][0]["joints"] == [0, 1, 2] and "mesh" in nodes[3]
        assert nodes[0]["children"] == [4] and nodes[4]["children"] == [1] and nodes[4]["scale"] == [1, 2, 0.5]
        assert nodes[1]["children"] == [5] and nodes[5]["children"] == [2] and nodes[1]["translation"] == [0, 0, 0]
        assert g["scenes"][0]["nodes"] == [0, 3]
        targets = sorted((c["target"]["node"], c["target"]["path"]) for c in g["animations"][0]["channels"])
        assert targets == [(1, "rotation"), (5, "scale"), (5, "translation")], targets
        assetc.cook(out, cooked)
        text = subprocess.check_output(["build/client/n3e-asset-check", str(cooked)], text=True).splitlines()
        moved = 0
        for line in text[1:6]:
            t, *v = map(float, line.split())
            for printed, corner in ((v[0:3], 1), (v[3:6], 6)):
                expected = ko_skinned(tree, t * 30, *corners[corner])
                assert max(abs(a - b) for a, b in zip(printed, expected)) < 1e-4, (player, t, corner, printed, expected)
                other = ko_skinned(tree, t * 30, *corners[corner], scale_first=True)
                moved = max(moved, max(abs(a - b) for a, b in zip(printed, other)))
        assert moved > 0.1, moved  # the fixture tells the two orders apart
    # A scale of 0 or below (static or in a track) is refused by name, and so
    # is a skeleton whose scale nodes would pass the 128-node scene.
    for bad in (joint_bytes("root", [0, 0, 0], [0, 0, 0, 1], [1, 0, 1]),
                joint_bytes("root", [0, 0, 0], [0, 0, 0, 1], [1, 1, 1], keys=(None, None, (1, [[1, 1, 1], [1, -1, 1]])))):
        try:
            ko.skeleton(bad, scaled=True)
        except ValueError as error:
            assert "KO joint scale not positive" in str(error), error
        else:
            raise AssertionError("non-positive joint scale accepted")
    chain = joint_bytes("j63", [0, 0.01, 0], [0, 0, 0, 1], [1, 1.5, 1])
    for i in range(62, -1, -1):
        chain = joint_bytes("j%d" % i, [0, 0.01, 0], [0, 0, 0, 1], [1, 1.5, 1], children=[chain])
    (root / "Joint.bin").write_bytes(chain)
    (root / "Skin.bin").write_bytes(skin)
    try:
        ko.convert(root, "character.bin", out, 0, 1.0)
    except ValueError as error:
        assert "past the 128-node scene" in str(error), error
    else:
        raise AssertionError("129-node scene accepted")
print(
    "PASS joint scale (PQ-266): a scaled joint converts as its node plus a translation and scale node, the client's "
    "skinned vertices match KO's rotate-then-scale arithmetic over the clip (static scale, scale track, gutter and "
    "no gutter) and not the other order, unscaled fixture at its pin, bounds readers still refuse, non-positive "
    "scales and a scene past 128 nodes refused"
)


# PQ-267 (D-175): skeletons past 64 joints; PQ-283 (D-176): skin vertices past
# four influences (evidence/pq-267-ko-character-skin-bounds.md,
# evidence/pq-283-ko-skin-many-influences.md). KO's skin load 004286f0 reads
# any number of influences and its skinning 00419f00 sums every one with the
# weights as read; its joint set 0041b000 has no joint bound. The reference is
# ko_skinned above (KO's arithmetic, not the converter's).
def gltf_rows(out, name):
    g = json.loads((out / "character.gltf").read_text())
    data = (out / "character.bin").read_bytes()
    a = g["accessors"][g["meshes"][0]["primitives"][0]["attributes"][name]]
    view = g["bufferViews"][a["bufferView"]]
    fmt = {5126: "4f", 5123: "4H"}[a["componentType"]]
    return [list(struct.unpack_from("<" + fmt, data, view["byteOffset"] + k * struct.calcsize(fmt)))
            for k in range(a["count"])]


def client_corners(cooked):
    # n3e-asset-check prints, at 0, 0.25, 0.5, 0.75 and 1 s, output vertices
    # 2 and 6, which are corners 1 and 6 (each triangle's winding reversed).
    text = subprocess.check_output(["build/client/n3e-asset-check", str(cooked)], text=True).splitlines()
    for line in text[1:6]:
        t, *v = map(float, line.split())
        yield t, {1: v[0:3], 6: v[3:6]}


def spoke(i, axis, scale=(1, 1, 1), turn=None):
    # `turn`: the joint's last rotation key's half angle (default 0.4 + 0.1 i).
    a = 0.4 + 0.1 * i if turn is None else turn
    q = [0, 0, 0, 1]
    q[axis] = math.sin(a)
    q[3] = math.cos(a)
    return ("j%d" % i, 0, [0.3 * (i % 7), 0.2 * (i % 5), 0.1 * (i % 3)], [0, 0, 0, 1], list(scale),
            (None, (1, [[0, 0, 0, 1], q]), None))


def star(count, scales={}, turn=None):
    # A root and count - 1 children, each turning about its own axis; joints
    # named in `scales` get that static scale (a PQ-266 scale node); `turn`
    # maps a joint to its spoke's half angle.
    tree = [("root", -1, [0, 0, 0], [0, 0, 0, 1], [1, 1, 1], (None, None, None))]
    tree += [spoke(i, i % 3, scales.get(i, (1, 1, 1)), turn(i) if turn else None) for i in range(1, count)]
    data = joint_bytes("root", *tree[0][2:5], children=[joint_bytes(n, *b[:3], keys=b[3]) for n, _, *b in tree[1:]])
    return tree, data


def converts(root, out, cooked, joints, points, materials=False, player=None):
    (root / "Joint.bin").write_bytes(joints)
    (root / "Skin.bin").write_bytes(scaled_skin(points))
    report = ko.convert(root, "character.bin", out, 0, 1.0, player=player)
    assetc.cook(out, cooked, materials=materials)
    return report


def refused(root, out, joints, points, reason, player=None):
    (root / "Joint.bin").write_bytes(joints)
    (root / "Skin.bin").write_bytes(scaled_skin(points))
    try:
        ko.convert(root, "character.bin", out, 0, 1.0, player=player)
    except ValueError as error:
        assert reason in str(error), error
    else:
        raise AssertionError("accepted: " + reason)


def looks_package(clips, out, engine):
    """`clips` (a cooked looks clip and its convert report) as the one looks
    entry of an engine `engine` package built on the PQ-249 template fixture,
    playing the clip in all four states; returns the package directory."""
    sys.path.append(str(pathlib.Path("tests").resolve()))
    import npc_looks_live
    from npc_templates_live import prepare as base
    import shutil
    clip, report = clips
    source = out.parent / (out.name + "-source")
    if source.exists():
        shutil.rmtree(source)
    shutil.copytree(base().parent / "source", source)
    (source / "npc-looks-src").mkdir()
    entry = dict(key="demo:looks/many", name_always=False, clips=[])
    for state in ("idle", "walk", "attack", "death"):
        shutil.copyfile(clip, source / "npc-looks-src" / (state + ".bin"))
        timing = ko.animation_metadata(report)
        timing["loop_blend"] = timing["loop_blend"] and state in ("idle", "walk")
        entry["clips"].append(dict(source="npc-looks-src/%s.bin" % state, **timing))
    m = json.loads((source / "package.json").read_text())
    template = dict(npc_looks_live.BASE, name="demo:creature/many", looks=entry["key"])
    m["gameplay"].update(spawns=[npc_looks_live.SPAWNS[0]], spawn_x=npc_looks_live.PLAYER[0],
                         spawn_z=npc_looks_live.PLAYER[1])
    m["npc"]["templates"] = [template]
    m["npc"]["slots"] = [dict(area=[0, 0, 0, 0], respawn_ticks=60, template=template["name"])]
    m["editing"]["spawns"] = [0]
    m["npc_looks"] = [entry]
    m.update(engine_version=engine, protocol_version=30)
    (source / "package.json").write_text(json.dumps(m))
    assetc.cook(source, out)
    return out


def looks_corners(package):
    """The client's skinned corners of looks entry 0 (n3e-asset-check --looks)
    at 0, 0.25, 0.5, 0.75 and 1 s: {time: [corner positions]}, each output
    triangle (a, c, b) mapped back to the converter's corners (a, b, c)."""
    text = subprocess.check_output(["build/client/n3e-asset-check", str(package), "--looks", "0"],
                                   text=True).splitlines()
    out = {}
    for line in text:
        t, *v = map(float, line.split())
        drawn = [v[3 * k:3 * k + 3] for k in range(len(v) // 3)]
        corners = [None] * len(drawn)
        for k, p in enumerate(drawn):
            corners[3 * (k // 3) + (0, 2, 1)[k % 3]] = p
        out[t] = corners
    return out


def forge(package, change, engine=40):
    """A copy of `package` with npc-looks-0.bin changed by `change(bytes)` and
    the release index rewritten (n3e's own index layout, tools/assetc/main.py)."""
    import shutil
    from common import digest, u
    tmp = tempfile.TemporaryDirectory(dir="build")
    out = pathlib.Path(tmp.name) / "release"
    shutil.copytree(package, out)
    files = {p.name: p.read_bytes() for p in out.iterdir() if p.name not in ("release.bin", "release.sha256")}
    files["npc-looks-0.bin"] = change(files["npc-looks-0.bin"])
    m = json.loads((out / "recipe.json").read_text())["manifest"]
    for p in out.iterdir():
        p.unlink()
    index = (b"N3R1" + u(1) + u(engine) + u(30) + string(m["game_id"]) + string(m["package_version"])
             + u(len(files)))
    for name, data in sorted(files.items()):
        (out / name).write_bytes(data)
        index += string(name) + u(len(data)) + digest(data)
    (out / "release.bin").write_bytes(index)
    (out / "release.sha256").write_text(digest(index).hex() + "\n")
    return tmp, out


def readers(package):
    """(client, server) exit codes and output on `package`."""
    import os
    results = []
    for cmd in [["build/client/n3e-asset-check", str(package)], ["target/debug/n3e-server", "--check-content"]]:
        p = subprocess.run(cmd, env={**os.environ, "N3E_PACKAGE": str(package)}, capture_output=True, text=True)
        results.append((p.returncode, p.stdout + p.stderr))
    return results


def first_four(influences):
    # Only the first four, renormalised (the influence table dropped).
    total = sum(w for _, w in influences[:4])
    return [(j, w / total) for j, w in influences[:4]]


def four_largest(influences):
    # D-175's retired reduction: the four largest weights, ties in file
    # order, renormalised, written out here rather than taken from the code.
    keep = sorted(sorted(range(len(influences)), key=lambda i: (-influences[i][1], i))[:4])
    total = sum(influences[i][1] for i in keep)
    return [(influences[i][0], influences[i][1] / total) for i in keep]


with tempfile.TemporaryDirectory() as td:
    root = pathlib.Path(td)
    for name, data in files.items():
        (root / name).write_bytes(data)
    (root / "Anim.bin").write_bytes(ints(1, 0) + f([0, 30, 30, 0, 0, 0, 0, 0]) + ints(0) + f([0, 0]) + string("turn"))
    out = pathlib.Path("build/check/ko-skin-bounds")
    cooked = out.parent / "ko-skin-bounds-cooked"
    plain = [(0, 1.0)]
    # The real data's shape (look 2600: 43 near-uniform influences over a
    # 43-joint skeleton; 2020: past 64 joints with a scale node), combined: 70
    # joints, joint 66 with a static non-uniform scale (a PQ-266 scale node).
    # Corner 1 has 43 influences on joints 0-40, 66 and 69; corner 4 five;
    # corner 6 six, one of weight 0 and joint 1 twice (KO sums both). Every
    # spoke turns by less than a half turn (half angle 0.2 + 0.01 i), so its
    # keys' dot product stays positive: KO's rotation interpolation 0064d002
    # is not read for the other case (PQ-284), where the converter's slerp
    # takes the shorter arc and ko_key above does not.
    tree, joints = star(70, {66: (1, 1.5, 0.8)}, lambda i: 0.2 + 0.01 * i)
    spread = list(range(41)) + [66, 69]
    raw = [1 + (k * 7) % 11 for k in range(43)]
    wide = [(j, r / sum(raw)) for j, r in zip(spread, raw)]
    five = [(1, 0.4), (2, 0.25), (3, 0.2), (4, 0.14), (5, 0.01)]
    six = [(6, 0.0), (5, 0.01), (1, 0.4), (66, 0.3), (4, 0.01), (1, 0.28)]
    points = [([0.2, 0.1, 0.0], plain), ([1.5, 0.4, 0.3], wide), ([0.1, 0.3, 0.0], plain),
              ([0.0, 0.0, 0.2], plain), ([0.3, 0.0, 0.1], five), ([0.0, 0.2, 0.3], plain),
              ([1.2, 1.4, -0.4], six), ([0.1, 0.1, 0.1], plain), ([0.2, 0.0, 0.3], plain)]
    # The strict reader (render detail, appearance) keeps refusing past four.
    try:
        ko.skins(scaled_skin(points))
    except ValueError as error:
        assert "skin vertex with 43 joint influences (1-4 supported)" in str(error), error
    else:
        raise AssertionError("43 influences accepted by the strict reader")
    report = converts(root, out, cooked, joints, points, materials=True)
    g = json.loads((out / "character.gltf").read_text())
    attributes = g["meshes"][0]["primitives"][0]["attributes"]
    assert sorted(attributes) == sorted(["POSITION", "NORMAL", "TEXCOORD_0"] + ["%s_%d" % (a, n) for n in range(11)
                                                                             for a in ("JOINTS", "WEIGHTS")])
    assert report["many_influences"] == {"vertices": 3, "most": 43, "sets": 11}, report["many_influences"]
    assert "reduced_influences" not in report
    # Skin joints: every weighted joint over all sets (0-40, 66, 69), so KO
    # joints 66 and 69 are skin joints 41 and 42; joint 66's scale node is 71.
    assert report["skin_joints"] == spread and g["skins"][0]["joints"] == spread, report["skin_joints"]
    assert report["scaled_joints"] == [{"joint": 66, "name": "j66", "scale_node": 71}], report["scaled_joints"]
    slot = {j: i for i, j in enumerate(spread)}
    for corner, influences in ((1, wide), (4, five), (6, six)):
        # Every influence as read, in file order, four a set, then padding.
        padded = influences + [(0, 0.0)] * (44 - len(influences))
        for n in range(11):
            js, ws = gltf_rows(out, "JOINTS_%d" % n)[corner], gltf_rows(out, "WEIGHTS_%d" % n)[corner]
            assert js == [slot[j] for j, _ in padded[4 * n:4 * n + 4]], (corner, n, js)
            assert max(abs(a - b) for a, b in zip(ws, [w for _, w in padded[4 * n:4 * n + 4]])) < 1e-6, (corner, n, ws)
    # The looks clip is N3SI: its table lists corners 1, 4 and 6 with every
    # influence past the first four that has weight.
    clip = (cooked / "scene.bin").read_bytes()
    assert clip[:4] == b"N3SI", clip[:4]
    sys.path.insert(0, str(pathlib.Path("tools/assetc").resolve()))
    import npc_looks
    _, _, tail, _ = npc_looks.split_scene(clip)
    nv = struct.unpack_from("<I", tail)[0]
    at = 4 + nv * 64
    table = []
    for _ in range(struct.unpack_from("<I", tail, at)[0]):
        vertex, n = struct.unpack_from("<II", tail, at + 4)
        table.append((vertex, [struct.unpack_from("<If", tail, at + 12 + 8 * k) for k in range(n)]))
        at += 8 + 8 * n
    assert [v for v, _ in table] == [1, 4, 6], table
    for (vertex, extra), influences in zip(table, (wide, five, six)):
        assert [j for j, _ in extra] == [slot[j] for j, w in influences[4:] if w > 0], (vertex, extra)
        assert max(abs(w - x) for (_, w), (_, x) in zip(extra, [p for p in influences[4:] if p[1] > 0])) < 1e-6
    # Any other cook of that glTF (the Moradon worm path, a player scene)
    # refuses the further sets, and the player path refuses by name.
    expect_bad(lambda: assetc.cook(out, out.parent / "ko-skin-refused"))
    refused(root, out, joints, points, "past four joint influences are drawn for NPC looks only", player=True)
    # The package: engine 40 (the cooker refuses it declared 39), N3NI, both
    # readers accept it.
    try:
        looks_package((cooked / "scene.bin", report), out.parent / "ko-skin-looks-39", 39)
    except ValueError as error:
        assert "incompatible" in str(error), error
    else:
        raise AssertionError("cooker accepted an N3NI looks model in an engine 39 package")
    package = looks_package((cooked / "scene.bin", report), out.parent / "ko-skin-looks", 40)
    assert (package / "npc-looks-0.bin").read_bytes()[:4] == b"N3NI"
    assert [code for code, _ in readers(package)] == [0, 0], readers(package)
    # The client's vertices are KO's full sum (every influence, weights as
    # read) and not the first four or the four largest.
    drawn = looks_corners(package)
    assert sorted(drawn) == [0, 0.25, 0.5, 0.75, 1], sorted(drawn)
    apart = {"first four": 0, "four largest": 0}
    for t, corners in drawn.items():
        for corner, (origin, influences) in enumerate(points):
            expected = ko_skinned(tree, t * 30, origin, influences)
            assert max(abs(a - b) for a, b in zip(corners[corner], expected)) < 1e-4, (t, corner, corners[corner], expected)
            if len(influences) > 4:
                for name, rule in (("first four", first_four), ("four largest", four_largest)):
                    apart[name] = max(apart[name], math.dist(corners[corner], ko_skinned(tree, t * 30, origin, rule(influences))))
    assert min(apart.values()) > 0.005, apart  # the fixture tells both apart (tolerance 1e-4)

    # The client reader's bounds on the influence table (the server checks
    # the header and budget only, as for every looks mesh).
    model = (package / "npc-looks-0.bin").read_bytes()
    table_at = len(model) - len(tail) + 4 + nv * 64

    def patch(offset, value, fmt="<I"):
        def change(data):
            data = bytearray(data)
            struct.pack_into(fmt, data, table_at + offset, value)
            return bytes(data)
        return change

    # Entry 0 (vertex 1, 39 influences) at +4, entry 1 (vertex 4, 1) at
    # +4 + 8 + 39 * 8, entry 2 (vertex 6) after it.
    second = 4 + 8 + 39 * 8
    for name, change, engine, why in [
            ("count 0", patch(0, 0), 40, "cooked count"), ("count past the vertices", patch(0, nv + 1), 40, "cooked count"),
            ("vertex past the mesh", patch(4, nv), 40, "influence vertex"),
            ("vertices out of order", patch(second, 1), 40, "influence vertex"),
            ("61 influences", patch(8, 61), 40, "cooked count"), ("0 influences", patch(8, 0), 40, "cooked count"),
            ("joint past the skin", patch(12, 43), 40, "influence joint"),
            ("weight 0", patch(16, 0.0, "<f"), 40, "influence weight"),
            ("negative weight", patch(16, -0.01, "<f"), 40, "influence weight"),
            ("weight NaN", patch(16, float("nan"), "<f"), 40, "finite"),
            ("weights past 1", patch(16, 0.5, "<f"), 40, "weight sum"),
            ("truncated", lambda d: d[:-1], 40, ""),
            ("N3NM magic over a table", lambda d: b"N3NM" + d[4:], 40, ""),
            ("N3MI magic over an RGB atlas", lambda d: b"N3MI" + d[4:], 40, ""),
            ("N3NI at engine 39", lambda d: d, 39, "npc looks model magic")]:
        tmp, bad = forge(package, change, engine)
        with tmp:
            (client, text), (server, server_text) = readers(bad)
            assert client != 0 and why in text, (name, text[-300:])
            if name == "N3NI at engine 39":
                assert server != 0 and "npc looks model header" in server_text, (name, server_text[-300:])

    # With render states (a double-sided part on a see-through DXT1 after the
    # opaque one, both on the many-influence skin): N3SJ clip, N3MI model.
    (root / "Character.bin").write_bytes(chrdata.replace(ints(1) + string("Part.bin"),
                                                         ints(2) + string("Part.bin") + string("Wing.bin")))
    (root / "Wing.bin").write_bytes(string("Wing.bin") + ints(0) + material_bytes(4) + string("Wing.dxt")
                                    + string("Skin.bin"))
    (root / "Wing.dxt").write_bytes(see_through)
    report = converts(root, out, cooked, joints, points, materials=True)
    assert report["many_influences"] == {"vertices": 6, "most": 43, "sets": 11}, report["many_influences"]
    assert (cooked / "scene.bin").read_bytes()[:4] == b"N3SJ"
    package = looks_package((cooked / "scene.bin", report), out.parent / "ko-skin-looks-materials", 40)
    assert (package / "npc-looks-0.bin").read_bytes()[:4] == b"N3MI"
    assert [code for code, _ in readers(package)] == [0, 0], readers(package)
    for t, corners in looks_corners(package).items():
        assert len(corners) == 18
        for corner in range(18):
            origin, influences = points[corner % 9]
            expected = ko_skinned(tree, t * 30, origin, influences)
            assert max(abs(a - b) for a, b in zip(corners[corner], expected)) < 1e-4, (t, corner, corners[corner], expected)
    (root / "Character.bin").write_bytes(chrdata)

    # The converter's bound (64 influences, 16 sets) and the glTF cooker's.
    refused(root, out, joints, points[:4] + [(points[4][0], [(1 + k % 5, 1 / 65) for k in range(65)])] + points[5:],
            "skin vertex with 65 joint influences (1-64 supported)")
    # A joint past the 70-joint skeleton in a further (fifth) influence is
    # refused: the skin reader bounds joints at 127 only.
    refused(root, out, joints, points[:4] + [(points[4][0], five[:4] + [(70, 0.01)])] + points[5:], "missing joint")
    (root / "Skin.bin").write_bytes(scaled_skin(points))
    ko.convert(root, "character.bin", out, 0, 1.0)
    good = (out / "character.gltf").read_text()

    def bad_gltf(change):
        g = json.loads(good)
        change(g["meshes"][0]["primitives"][0]["attributes"])
        (out / "character.gltf").write_text(json.dumps(g))
        expect_bad(lambda: assetc.cook(out, out.parent / "ko-skin-refused", materials=True))
        (out / "character.gltf").write_text(good)

    bad_gltf(lambda a: a.pop("WEIGHTS_10"))  # a joint set without its weights
    bad_gltf(lambda a: a.update({"JOINTS_%d" % n: a["JOINTS_1"] for n in range(11, 16)} |
                                {"WEIGHTS_%d" % n: a["WEIGHTS_10"] for n in range(11, 16)} |
                                {"JOINTS_16": a["JOINTS_1"], "WEIGHTS_16": a["WEIGHTS_10"]}))  # 17 sets
    bad_gltf(lambda a: a.update(WEIGHTS_9=a["WEIGHTS_1"]))  # the weights no longer sum to 1
    bad_gltf(lambda a: a.update(JOINTS_12=a["JOINTS_1"], WEIGHTS_12=a["WEIGHTS_10"]))  # a gap in the sets
    assetc.cook(out, cooked, materials=True)
    assert (cooked / "scene.bin").read_bytes() == clip

    # Past 64 joints: 70 joints, of which corner 1 uses 3, 66 and 69 and every
    # other corner the root, so the skin has 4 joints and every joint a node.
    # Joint 66 has a static non-uniform scale, so its scale node (PQ-266)
    # follows the mesh node, as look 2020's do.
    tree, joints = star(70, {66: (1, 1.5, 0.8)})
    wide = [(3, 0.5), (66, 0.3), (69, 0.2)]
    points = [([0.2, 0.1, 0.0], plain), ([1.5, 0.4, 0.3], wide), ([0.1, 0.3, 0.0], plain),
              ([0.0, 0.0, 0.2], plain), ([0.3, 0.0, 0.1], plain), ([0.0, 0.2, 0.3], plain),
              ([1.2, 1.4, -0.4], [(66, 1.0)]), ([0.1, 0.1, 0.1], plain), ([0.2, 0.0, 0.3], plain)]
    try:
        ko.skeleton(joints)
    except ValueError as error:
        # The bounds readers keep 64 joints (and 64 children of one joint).
        assert str(error) in ("skeleton bound", "count out of bounds"), error
    else:
        raise AssertionError("70 joints accepted by the bounds readers' skeleton")
    report = converts(root, out, cooked, joints, points)
    g = json.loads((out / "character.gltf").read_text())
    assert report["skin_joints"] == [0, 3, 66, 69] and g["skins"][0]["joints"] == [0, 3, 66, 69]
    assert len(g["nodes"]) == 72 and "mesh" in g["nodes"][70] and report["joint_count"] == 70
    assert report["scaled_joints"] == [{"joint": 66, "name": "j66", "scale_node": 71}], report["scaled_joints"]
    assert max(abs(a - b) for a, b in zip(g["nodes"][71]["scale"], [1, 1.5, 0.8])) < 1e-6
    assert g["nodes"][71]["children"] == [66]
    assert 71 in g["nodes"][0]["children"] and 66 not in g["nodes"][0]["children"]
    assert gltf_rows(out, "JOINTS_0")[1][:3] == [1, 2, 3] and gltf_rows(out, "JOINTS_0")[6][0] == 2
    for t, printed in client_corners(cooked):
        for corner in (1, 6):
            expected = ko_skinned(tree, t * 30, *points[corner])
            assert max(abs(a - b) for a, b in zip(printed[corner], expected)) < 1e-4, (t, corner, printed, expected)
    # 65 weighted joints are refused, and so are 128 joints.
    many = [(p, [(1 + k, 1.0)]) for k, (p, _) in enumerate(points)]
    many = many + [(points[0][0], [(10 + k, 1.0)]) for k in range(55)] + [(points[0][0], plain)] * 2
    refused(root, out, joints, many, "65 weighted KO joints past the skin's 64")  # joints 0-64
    refused(root, out, star(128)[1], points, "skeleton bound")
    # At most 64 joints, every joint stays in the skin (as before PQ-267).
    tree, joints = star(64)
    report = converts(root, out, cooked, joints, [(p, [(min(j, 63), w) for j, w in inf]) for p, inf in points])
    assert json.loads((out / "character.gltf").read_text())["skins"][0]["joints"] == list(range(64))
    assert "skin_joints" not in report and "many_influences" not in report
print(
    "PASS skin bounds (PQ-267, PQ-283): a vertex past four influences keeps every influence as read in glTF "
    "JOINTS_n/WEIGHTS_n (with a skin past 64 joints and a scale node), cooks as an N3SI/N3SJ looks clip and an "
    "N3NI/N3MI model in an engine 40 package both readers accept, and the client's vertices match KO's full sum, "
    "not the first or largest four; the client refuses forged influence tables, the cooker engine 39, other cooks "
    "and the player path the further sets, 65 influences and malformed sets refused; a skeleton past 64 joints "
    "(one with a scale node) skins with its weighted joints in order and matches KO's arithmetic, 65 weighted "
    "joints and 128 joints refused, 64 joints keep every joint; the strict readers keep their bounds"
)


# PQ-281 (D-177; evidence/pq-281-ko-skin-nonfinite-normals.md): KO draws a
# part vertex with its normal as loaded (mesh load 00440870, skinning
# 00419f00 writes positions only, vertex build 004401b0 / 00440440 copies the
# normal), so a zero normal has no direction for n3e's direction-only
# lighting. The converter writes such a drawn corner (non-finite, or squared
# length below the cooker's 1e-12) with its own triangle's unit normal, the
# side the loaded normals face, and keeps every other normal as read. The
# shapes are the operator's: a zero normal, a tail normal of length about
# 1e-8, a two-sided sheet whose shared vertices have zero normals (their face
# sum cancels), a drawn non-finite normal and an undrawn NaN one (the harpy's).
def normal_skin(vertices, indices):
    """One LOD of `vertices` ((position, normal) on joint 0) drawn by
    `indices`, one UV a vertex."""
    n = len(vertices)
    out = string("skins") + string("lod0") + ints(len(indices) // 3, n, n)
    out += b"".join(struct.pack("<6f", *p, *nrm) for p, nrm in vertices)
    out += struct.pack("<%dH" % len(indices), *indices)
    out += b"".join(f([0.1 + 0.08 * k, 0.2]) for k in range(n))
    out += struct.pack("<%dH" % len(indices), *indices)
    for p, _ in vertices:
        out += f(p) + ints(1) + bytes(8) + ints(0)
    return out + (string("empty") + ints(0, 0, 0)) * 3


def normal_rows(out):
    g = json.loads((out / "character.gltf").read_text())
    data = (out / "character.bin").read_bytes()
    a = g["accessors"][g["meshes"][0]["primitives"][0]["attributes"]["NORMAL"]]
    view = g["bufferViews"][a["bufferView"]]
    return [list(struct.unpack_from("<3f", data, view["byteOffset"] + 12 * k)) for k in range(a["count"])]


def f32(*v):
    return list(struct.unpack("<%df" % len(v), struct.pack("<%df" % len(v), *v)))


with tempfile.TemporaryDirectory() as td:
    root = pathlib.Path(td)
    for name, data in files.items():
        (root / name).write_bytes(data)
    out = pathlib.Path("build/check/ko-normals")
    cooked = out.parent / "ko-normals-cooked"
    nan, inf = float("nan"), float("inf")
    tail = [-1.4901161193847656e-08, 0.0, 1.862645149230957e-09]  # look 3800's tail, length 1.5e-8
    vertices = [([0, 0, 0], [0, 0, 0]), ([1, 0, 0], tail), ([0, 1, 0], [0, 0, 0.95]),  # triangle 0
                ([2, 0, 0], [0, 0, 0]), ([2, 1, 0], [0, 0, 0]), ([2, 0, 1], [0, 0, 0]),  # the sheet
                ([0, 0, 3], [nan, 0, 1]), ([1, 0, 3], [inf, 0, 0]), ([0, 1, 3], [0, 0.6, 0.8]),
                ([5, 5, 5], [nan, nan, nan])]  # vertex 9: undrawn
    indices = [0, 1, 2, 3, 4, 5, 3, 5, 4, 6, 7, 8]  # the sheet: (3, 4, 5) and (3, 5, 4)
    skin_data = normal_skin(vertices, indices)
    # The strict readers (render detail, appearance) keep refusing the NaN.
    expect_bad(lambda: ko.skins(skin_data))
    assert ko.skins(skin_data, every=True)[1][0]["vertices"][9][3:] != [0, 0, 0]
    (root / "Skin.bin").write_bytes(skin_data)
    # Expected, from the geometry (n3e mirrors z): triangle 0 and triangle 3
    # face +z, as vertex 2's and 8's loaded normals do; the sheet's two
    # triangles face +x and -x.
    up, front, back = [0, 0, -1], [1, 0, 0], [-1, 0, 0]
    expected = [up, up, f32(0, 0, -0.95), front, front, front, back, back, back, up, up, f32(0, 0.6, -0.8)]
    for player in (False, True):
        report = ko.convert(root, "character.bin", out, 0, 1.0, player=player)
        rows = normal_rows(out)
        assert len(rows) == 12 and all(r == e for r, e in zip(rows, expected)), (player, rows)
        assert report["rebuilt_normals"] == {"vertices": 7, "corners": 10}, report["rebuilt_normals"]
    assetc.cook(out, cooked)
    clip = (cooked / "scene.bin").read_bytes()
    assert clip[:4] == b"N3S1", clip[:4]
    sys.path.insert(0, str(pathlib.Path("tools/assetc").resolve()))
    import npc_looks
    _, _, scene_tail, _ = npc_looks.split_scene(clip)
    assert struct.unpack_from("<I", scene_tail)[0] == 12
    cooked_normals = [list(struct.unpack_from("<3f", scene_tail, 4 + 64 * k + 12)) for k in range(12)]
    assert cooked_normals == rows, cooked_normals
    # As a looks model (N3NM, engine 38) both readers accept it.
    package = looks_package((cooked / "scene.bin", report), out.parent / "ko-normals-looks", 38)
    assert (package / "npc-looks-0.bin").read_bytes()[:4] == b"N3NM"
    assert [code for code, _ in readers(package)] == [0, 0], readers(package)
    # A corner without a normal on a zero-area triangle is refused by name.
    (root / "Skin.bin").write_bytes(normal_skin([([0, 0, 0], [0, 0, 0]), ([1, 0, 0], [0, 0, 1]),
                                                 ([2, 0, 0], [0, 0, 1])], [0, 1, 2]))
    try:
        ko.convert(root, "character.bin", out, 0, 1.0)
    except ValueError as error:
        assert "KO skin vertex without a normal on a zero-area triangle" in str(error), error
    else:
        raise AssertionError("zero-area triangle without a normal accepted")
    # Every normal with a direction converts as read (no rebuilt_normals), and
    # the cooker still refuses a normal shorter than its bound.
    (root / "Skin.bin").write_bytes(normal_skin([([0, 0, 0], [0, 0, 2]), ([1, 0, 0], [0, 0.6, 0.8]),
                                                 ([0, 1, 0], [0, 0, 0.95])], [0, 1, 2]))
    report = ko.convert(root, "character.bin", out, 0, 1.0)
    assert "rebuilt_normals" not in report, report
    assert normal_rows(out) == [[0, 0, -2], f32(0, 0.6, -0.8), f32(0, 0, -0.95)], normal_rows(out)
    good = (out / "character.gltf").read_text()
    data = bytearray((out / "character.bin").read_bytes())
    g = json.loads(good)
    view = g["bufferViews"][g["accessors"][g["meshes"][0]["primitives"][0]["attributes"]["NORMAL"]]["bufferView"]]
    struct.pack_into("<3f", data, view["byteOffset"], *tail)
    (out / "character.bin").write_bytes(bytes(data))
    expect_bad(lambda: assetc.cook(out, out.parent / "ko-normals-refused"))
print(
    "PASS KO skin normals (PQ-281): a drawn corner whose normal is zero, about 1e-8 long, NaN or infinite converts "
    "as its own triangle's unit normal on the side the loaded normals face (both sides of a two-sided sheet whose "
    "shared vertices have zero normals), on the NPC and player paths; every other normal as read; an undrawn NaN "
    "normal is not written; the clip cooks as N3S1 with those normals and its N3NM looks package passes both "
    "readers; a zero-area triangle refused by name; the strict readers and the cooker keep their refusals"
)
