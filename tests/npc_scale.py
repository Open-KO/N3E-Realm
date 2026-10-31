"""PQ-272 per-template NPC drawn scale (N3N4, engine 41 / wire 30): both
readers on the synthetic package of tests/npc_scale_live.py, and forged scales,
engines and models failing closed in both. No KO data, no containers.

KO carries a template's sSize to the client in the NPC-in record (AI
00438c42 -> 004221d5, Ebenezer 00479e7c, client 005cd6d5) and the client
scales the character by sSize x 0.01 (005cdd82, 0041f800, 0043b650);
evidence/pq-272-ko-npc-drawn-scale.md labels each claim.
"""
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path("tools/assetc").resolve()))
sys.path.append(str(Path("tests").resolve()))
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402

import main  # noqa: E402
import npc  # noqa: E402
from common import digest, string, u  # noqa: E402
import npc_looks_live  # noqa: E402
import npc_scale_live  # noqa: E402


def readers(out, good, why="", label=""):
    for cmd in [["build/client/n3e-asset-check", str(out)], ["target/debug/n3e-server", "--check-content"]]:
        p = subprocess.run(cmd, env={**os.environ, "N3E_PACKAGE": str(out)}, capture_output=True, text=True)
        assert (p.returncode == 0) == good, (cmd, label or why, p.stdout[-400:], p.stderr[-400:])
        if not good and why:
            assert why in p.stderr, (cmd, why, p.stderr[-400:])


def check(source, change, good, why="", label="", engine=41, protocol=30):
    """Both readers on a copy of `source` with its files changed by
    `change(files)` and re-indexed at `engine` (as tests/npc_looks.py forges)."""
    with tempfile.TemporaryDirectory(dir="build") as tmp:
        out = Path(tmp) / "release"
        shutil.copytree(source, out)
        files = {p.name: p.read_bytes() for p in out.iterdir() if p.name not in ("release.bin", "release.sha256")}
        m = json.loads((out / "recipe.json").read_text())["manifest"]
        change(files)
        for p in out.iterdir():
            p.unlink()
        index = (b"N3R1" + u(1) + u(engine) + u(protocol) + string(m["game_id"]) + string(m["package_version"])
                 + u(len(files)))
        for name, data in sorted(files.items()):
            (out / name).write_bytes(data)
            index += string(name) + u(len(data)) + digest(data)
        (out / "release.bin").write_bytes(index)
        (out / "release.sha256").write_text(digest(index).hex() + "\n")
        readers(out, good, why, label)

package = npc_scale_live.prepare()
data = (package / "npc.bin").read_bytes()
assert data[:8] == b"N3N4" + struct.pack("<I", 4)
manifest = json.loads((package / "recipe.json").read_text())["manifest"]
assert (manifest["engine_version"], manifest["protocol_version"]) == (41, 30)
lines = npc_looks_live.check_readers(package)
assert any(line.startswith("npc looks 1 texture_bytes 48 ") for line in lines), lines
check(package, lambda f: None, True)

# The two scales: the pillar's default 100 and the giant's 200, each the u32
# after its template's tracing range (8.0 m in this fixture); the giant's
# template is the second.
tracing = struct.pack("<f", 8.0)
ats = [i + 4 for i in range(len(data)) if data[i:i + 4] == tracing]
assert [struct.unpack_from("<I", data, at)[0] for at in ats] == [100, 200], ats


def scale(value, at=ats[1]):
    out = bytearray(data)
    struct.pack_into("<I", out, at, value)
    return bytes(out)


for value in (0, 1001, 0xFFFFFFFF):
    check(package, lambda f, d=scale(value): f.update({"npc.bin": d}), False, "npc template scale",
          label=f"scale {value}", engine=41)
for edge in (1, 1000):
    check(package, lambda f, d=scale(edge): f.update({"npc.bin": d}), True, label=f"scale {edge}", engine=41)
# N3N4 below engine 41, N3N3 at 41 (the PQ-253 package) and N3N4 bytes under
# N3N3's magic and model all fail closed.
check(package, lambda f: None, False, "npc scale compatibility", engine=40)
check(npc_looks_live.prepare(), lambda f: None, False, "npc scale compatibility", engine=41)
check(package, lambda f: f.update({"npc.bin": b"N3N3" + struct.pack("<I", 3) + data[8:]}), False, engine=41,
      label="N3N4 layout under N3N3")
check(package, lambda f: f.update({"npc.bin": data + b"\0"}), False, engine=41, label="trailing")
print("PASS both readers accept the engine 41 N3N4 package (scales 100 and 200, and 1 and 1,000) and refuse "
      "scales 0, 1,001 and 2^32-1, N3N4 at engine 40, N3N3 at engine 41, N3N4 bytes as N3N3 and trailing bytes")

# The cooker: a scale needs the looks table; a policy without one keeps N3N3
# byte for byte at engine 38-40; a scaled policy declared below engine 41 is refused.
source = npc_scale_live.OUT / "source"
m = json.loads((source / "package.json").read_text())


def cooks(change):
    with tempfile.TemporaryDirectory(dir="build") as tmp:
        root = Path(tmp) / "source"
        shutil.copytree(source, root)
        changed = json.loads(json.dumps(m))
        change(changed)
        (root / "package.json").write_text(json.dumps(changed))
        try:
            main.cook(root, Path(tmp) / "out")
        except ValueError as error:
            return str(error)
        return None


assert cooks(lambda c: None) is None
assert cooks(lambda c: c.update(engine_version=38)) == "incompatible schema/engine/protocol"
assert cooks(lambda c: c.pop("npc_looks")) == "npc scale requires npc looks"
unscaled = lambda c: [t.pop("scale", None) for t in c["npc"]["templates"]]  # noqa: E731
assert cooks(lambda c: (unscaled(c), c.update(engine_version=41))) == "incompatible schema/engine/protocol"
assert cooks(lambda c: (unscaled(c), c.update(engine_version=38))) is None
assert not npc.scaled({"templates": [dict(name="x")]}) and npc.scaled({"templates": [dict(scale=100)]})
print("PASS N3N4 cooker: engine 41 exactly when a template carries a scale, never without the looks table")
