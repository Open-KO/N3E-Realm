#!/usr/bin/env python3
"""Reproduce the original demo's eleven clips and bitmap HUD, without KO inputs."""
import json
import re
from pathlib import Path
import shutil
import math
import struct
import tempfile
import animation
import main
from common import u, f, string


def generate(root):
    # Original two-joint block figure. Closed boxes remain visible from all camera angles.
    g = json.loads(Path("tests/fixtures/legacy-demo/fixture.gltf").read_text())
    old = Path("tests/fixtures/legacy-demo/fixture.bin").read_bytes()
    positions = []
    normals = []
    uvs = []
    joints = []
    weights = []
    indices = []
    faces = [
        ([0, 4, 6, 2], [-1, 0, 0]),
        ([1, 3, 7, 5], [1, 0, 0]),
        ([0, 1, 5, 4], [0, -1, 0]),
        ([2, 6, 7, 3], [0, 1, 0]),
        ([0, 2, 3, 1], [0, 0, -1]),
        ([4, 5, 7, 6], [0, 0, 1]),
    ]
    for x, y, z, sx, sy, sz, joint in [
        (0, 1.05, 0, 0.22, 0.30, 0.14, 1),
        (0, 1.55, 0, 0.16, 0.18, 0.16, 1),
        (-0.12, 0.36, 0, 0.085, 0.36, 0.1, 0),
        (0.12, 0.36, 0, 0.085, 0.36, 0.1, 0),
        (-0.32, 1.02, 0, 0.08, 0.29, 0.09, 1),
        (0.32, 1.02, 0, 0.08, 0.29, 0.09, 1),
    ]:
        corners = [
            [
                x + (sx if i & 1 else -sx),
                y + (sy if i & 2 else -sy),
                z + (sz if i & 4 else -sz),
            ]
            for i in range(8)
        ]
        for face, normal in faces:
            start = len(positions)
            for index, uv in zip(face, [[0, 0], [1, 0], [1, 1], [0, 1]]):
                positions.append(corners[index])
                normals.append(normal)
                uvs.append(uv)
                joints.append([joint, 0, 0, 0])
                weights.append([1, 0, 0, 0])
            indices.extend(start + i for i in [0, 1, 2, 0, 2, 3])

    def pack(rows, kind):
        return struct.pack(
            "<" + kind * sum(map(len, rows)), *[v for row in rows for v in row]
        )

    chunks = [
        pack(positions, "f"),
        pack(normals, "f"),
        pack(uvs, "f"),
        pack(joints, "H"),
        pack(weights, "f"),
        struct.pack("<" + "H" * len(indices), *indices),
        old[236:364],
        old[364:376],
        old[376:424],
    ]
    offset = 0
    for i, chunk in enumerate(chunks):
        g["bufferViews"][i].update(byteOffset=offset, byteLength=len(chunk))
        offset += len(chunk)
        if i < 6:
            g["accessors"][i]["count"] = len(indices) if i == 5 else len(positions)
        g["accessors"][i].pop("min", None)
        g["accessors"][i].pop("max", None)
    g["buffers"][0]["byteLength"] = offset
    g["extras"]["n3e_instance_scale"] = [1, 1, 1]
    g["asset"]["generator"] = "n3e KO-11 original block figure"
    (root / "fixture.gltf").write_text(json.dumps(g, indent=2) + "\n")
    (root / "fixture.bin").write_bytes(b"".join(chunks))
    with tempfile.TemporaryDirectory(dir="build") as td:
        source = Path(td)
        shutil.copytree("tests/fixtures/legacy-demo", source, dirs_exist_ok=True)
        meta = json.loads((source / "scene.json").read_text())
        meta["instance_scale"] = [1, 1, 1]
        (source / "scene.json").write_text(json.dumps(meta))
        (source / "fixture.gltf").write_text(json.dumps(g))
        for i, name in enumerate(animation.NAMES):
            state = i if i < 7 else i - 7
            angles = {
                0: [0, 0.1, 0],
                1: [-0.4, 0.4, -0.4],
                2: [0, -1, 0],
                3: [0, 1.3, 1.5],
                4: [-0.7, 0.7, -0.7],
                5: [0.4, -0.4, 0.4],
                6: [0.35, 0.4, 0.35],
            }[state]
            chunks[8] = pack(
                [[0, 0, math.sin(a / 2), math.cos(a / 2)] for a in angles], "f"
            )
            (source / "fixture.bin").write_bytes(b"".join(chunks))
            main.cook(source, source / "cooked")
            shutil.copyfile(source / "cooked/scene.bin", root / name)
    # The original runtime bitmap alphabet also supplies the distributable atlas.
    alphabet = re.findall(r'"([01/]{41})"', Path("client/render/hud.h").read_text())[
        :36
    ]
    glyphs = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", alphabet))
    glyphs.update({c: glyphs[c.upper()] for c in "abcdefghijklmnopqrstuvwxyz"})
    glyphs.update(
        {
            "/": "00001/00001/00010/00100/01000/10000/10000",
            "-": "00000/00000/00000/11111/00000/00000/00000",
            ":": "00000/00100/00100/00000/00100/00100/00000",
        }
    )
    atlas = bytearray(256 * 128 * 4)
    for code in range(33, 127):
        bits = glyphs.get(chr(code), "11111/10001/00010/00100/00100/00000/00100").split(
            "/"
        )
        ox = ((code - 32) % 16) * 16
        oy = ((code - 32) // 16) * 20
        for y in range(10):
            for x in range(6):
                if bits[y * 7 // 10][x * 5 // 6] == "1":
                    at = ((oy + y) * 256 + ox + x) * 4
                    atlas[at : at + 4] = b"\xff" * 4
    records = []

    def record(
        kind,
        rect,
        binding="",
        text="",
        anchor=(0, 0),
        color=0xFFFFFFFF,
        target=0,
        texture=0,
    ):
        records.append(
            u(kind)
            + f(anchor)
            + f(rect)
            + u(texture)
            + f([0, 0, 1, 1])
            + string(binding)
            + string(text)
            + u(color)
            + u(target)
            + u(0)
        )

    def panel(rect, anchor=(0, 0), target=0):
        record(0, rect, anchor=anchor, target=target, texture=1)

    panel([12, 12, 290, 106])
    panel([-160, 12, 160, 84], (0.5, 0), 1)
    for rect, binding, color in [
        ([24, 44, 275, 62], "health", 0xFFFF6060),
        ([24, 70, 275, 88], "resource", 0xFF6090FF),
    ]:
        record(0, rect, binding, texture=2 if binding == "health" else 3)
    record(1, [24, 20, 275, 40], "player_name")
    record(1, [30, 45, 270, 65], "health_text")
    record(1, [30, 71, 270, 91], "resource_text")
    record(1, [-145, 22, 145, 77], "target_name", anchor=(0.5, 0), target=1)
    panel([12, -178, 510, -80], (0, 1))
    panel([520, -178, 1014, -80], (0, 1))
    record(1, [24, -168, 495, -132], "chat", anchor=(0, 1))
    record(1, [24, -116, 495, -88], "chat_input", anchor=(0, 1))
    record(2, [12, -178, 510, -80], "chat", anchor=(0, 1))
    record(1, [532, -168, 1000, -85], "combat", anchor=(0, 1))
    # PQ-408 (D-211): the message line's scroll bar in the panel's right margin:
    # up and down buttons, a track and its thumb (the demo's own drawing).
    for rect, binding, texture in [
        ([1001, -176, 1012, -165], "message_up", 5),
        ([1001, -165, 1012, -94], "message_track", 6),
        ([1001, -94, 1012, -83], "message_down", 5),
    ]:
        record(0, rect, anchor=(0, 1), texture=texture)
        record(2, rect, binding, anchor=(0, 1))
    record(0, [1001, -165, 1012, -151], "message_thumb", anchor=(0, 1), texture=4)
    panel([12, -72, 1014, -12], (0, 1))
    panel([24, -62, 164, -24], (0, 1))
    record(1, [34, -55, 155, -25], text="R / SPACE / 1\nATTACK", anchor=(0, 1))
    record(2, [24, -62, 164, -24], "strike", anchor=(0, 1))
    record(0, [185, -34, 625, -23], "xp", anchor=(0, 1), texture=4)
    record(1, [185, -59, 630, -38], "xp_text", anchor=(0, 1))
    record(
        1,
        [660, -59, 1000, -24],
        text="TAB TARGET / ENTER CHAT\nF LOOT / E RESPAWN",
        anchor=(0, 1),
    )
    textures = [
        (256, 128, atlas),
        (1, 1, bytes([20, 27, 33, 240])),
        (1, 1, bytes([164, 45, 45, 255])),
        (1, 1, bytes([40, 95, 165, 255])),
        (1, 1, bytes([190, 160, 55, 255])),
        (1, 1, bytes([96, 116, 136, 255])),
        (1, 1, bytes([44, 56, 68, 255])),
    ]
    data = b"N3H1" + u(0) + f([60, 20]) + u(len(textures))
    for w, h, pixels in textures:
        data += u(w) + u(h) + pixels
    # PQ-407 (D-210): the message line keeps two messages ahead of the combat
    # status (five 16-unit rows fit the panel), a server refusal in amber and
    # a client notice in light blue (the demo's own choice).
    messages = b"N3HM" + u(2) + u(0xFFFFD060) + u(0xFFA0D0FF)
    # PQ-408 (D-211): a short history, so the refusal replay reaches the line
    # limit: 12 messages and 6 lines kept, steps of 1 and 2 lines, a held button
    # repeating after half a second.
    messages += b"N3HS" + u(12) + u(6) + u(1) + u(2) + f([0.5])
    (root / "hud.bin").write_bytes(data + u(len(records)) + b"".join(records) + messages)


if __name__ == "__main__":
    generate(Path("games/demo"))
