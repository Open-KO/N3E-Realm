"""Opt-in real local KO conversion and numeric/runtime compatibility evidence.
Outputs stay in ignored build/. Run from the repository root after make client.
"""

import json
import math
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools/assetc"))
import ko_character as ko
import main as assetc

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "assets/ko")
source = "Chr/mob_worm.n3chr"
assets = ko.Assets(root)
ch = ko.character(assets.get(source))
bones = ko.skeleton(assets.get(ch["joint"]))
clips = ko.animations(assets.get(ch["animation"]))
p = ko.part(assets.get(ch["parts"][0]))
_, lods = ko.skins(assets.get(p["skin"]))
skin = lods[0]


def world(frame):
    matrices = []
    for b in bones:
        translation = ko.sample(b["keys"][0], frame, b["translation"])
        rotation = ko.sample(b["keys"][1], frame, b["rotation"])
        local = ko.matrix(translation, rotation)
        matrices.append(
            ko.multiply(matrices[b["parent"]], local) if b["parent"] >= 0 else local
        )
    return matrices


inverses = [ko.inverse(m) for m in world(0)]


def vertex(index, frame):
    matrices = world(frame)
    p = skin["origins"][index] + [1.0]
    result = [0.0, 0.0, 0.0]
    for joint, weight in zip(skin["joints"][index], skin["weights"][index]):
        m = ko.multiply(matrices[joint], inverses[joint])
        for i in range(3):
            result[i] += weight * sum(m[i][j] * p[j] for j in range(4))
    return [result[0], result[1], -result[2]]


reports = []
for name, clip_index in [("walk", 1), ("attack", 4)]:
    out = pathlib.Path("build/ko-source") / name
    cooked = pathlib.Path("build/packages") / (
        "kotest" if name == "walk" else "kotest-attack"
    )
    info = ko.convert(root, source, out, clip_index, 1.0)
    digest = assetc.cook(out, cooked)
    ko.convert(root, source, out, clip_index, 1.0)
    assert assetc.cook(out, cooked) == digest
    cpp = subprocess.check_output(
        ["build/client/n3e-asset-check", str(cooked)], text=True
    ).splitlines()
    rust = subprocess.check_output(
        ["target/debug/n3e-server", "--check-content"],
        env={**os.environ, "N3E_PACKAGE": str(cooked)},
        text=True,
    ).splitlines()
    assert cpp[0] == rust[0] == digest
    maximum = 0.0
    clip = clips[clip_index]
    for line in cpp[1:6]:
        t, *actual = map(float, line.split())
        frame = clip["start"] + min(t, info["duration_seconds"]) * clip["fps"]
        # C++ reports expanded triangle corners 2 and 6. Reflection swaps corners 1/2.
        expected = vertex(skin["indices"][1], frame) + vertex(skin["indices"][6], frame)
        maximum = max(maximum, max(abs(a - b) for a, b in zip(actual, expected)))
    assert maximum < 0.001, maximum
    reports.append(
        {
            "clip": name,
            "release": digest,
            "max_pose_error_m": maximum,
            "source_files": info["sources"],
            "joints": info["joint_count"],
            "vertices": info["render_vertices"],
        }
    )
pathlib.Path("build/ko-source/verification.json").write_text(
    json.dumps(reports, indent=2) + "\n"
)
print(json.dumps(reports, indent=2))
print(
    "PASS real local KO walk/attack deterministic cooking, C++/Rust identity and source-space skinning agreement <1mm"
)
