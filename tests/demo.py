"""KO-11 package identities, readers, original provenance and reuse boundary."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path("tools/assetc").resolve()))
import main, demo_variants, demo_presentation

binaries = [
    Path("build/client/n3e-client"),
    Path("build/client-tools/n3e-client"),
    Path("target/debug/n3e-server"),
]


def hashes():
    return {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in binaries
        if p.exists()
    }


before = hashes()
base = main.cook(Path("games/demo"), Path("build/packages/demo"))
alt = demo_variants.cook()
assert base != (alt / "release.sha256").read_text().strip()
with tempfile.TemporaryDirectory(dir="build") as td:
    root = Path(td)
    demo_presentation.generate(root)
    for path in root.iterdir():
        assert path.read_bytes() == (Path("games/demo") / path.name).read_bytes(), path
for name in ["demo", "demo-alt"] + (["demo-ko"] if "--ko" in sys.argv else []):
    package = Path("build/packages") / name
    expected = (package / "release.sha256").read_text().strip()
    for command, env in [
        (["build/client/n3e-asset-check", str(package)], os.environ),
        (
            ["target/debug/n3e-server", "--check-content"],
            {**os.environ, "N3E_PACKAGE": str(package)},
        ),
    ]:
        p = subprocess.run(command, env=env, capture_output=True, text=True, check=True)
        assert p.stdout.splitlines()[0] == expected
if "--ko" in sys.argv:
    for name in [
        "gameplay.bin",
        "progression.bin",
        "collision.bin",
        "camera.bin",
        "melee.bin",
        "damage.bin",
        "npc.bin",
        "life.bin",
    ]:
        assert (Path("build/packages/demo") / name).read_bytes() == (
            Path("build/packages/demo-ko") / name
        ).read_bytes(), name
assert before == hashes()
out = Path("build/ko-11/boundary.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(
    json.dumps(
        {
            "binaries": before,
            "packages": {
                name: (Path("build/packages") / name / "release.sha256")
                .read_text()
                .strip()
                for name in ["demo", "demo-alt"]
                + (["demo-ko"] if "--ko" in sys.argv else [])
            },
        },
        indent=2,
    )
    + "\n"
)
print(
    "PASS original clip/HUD reproduction; C++/Rust readers; alternate package uses unchanged binaries; optional artwork retains gameplay"
)
