"""RQ-163: player clips past four joint influences (N3SI, engine 43).

A KO race whose skin has drawn vertices with more than four joint influences
(the Arch Tuarek: 49 lower-part vertices with five) keeps every influence on
the player path, as KO's skinning 00419f00 sums them (PQ-283, D-176; a player
is a CN3Chr as an NPC is, source PlayerBase.h). Its player clips cook as N3SI,
N3S1 with D-176's influence table, and a package with them is engine 43
(content/animation.md, "Influence tables on the player path").

On the PQ-253 engine 38 fixture (tests/npc_looks_live.py, synthetic), every
player clip (player-<state>.bin, the combat clips' source, player-skill-0.bin)
is rewritten so that its joint-1 vertices weigh joint 1 at 0.5 in their four
slots and joint 0 at 0.5 in the influence table, and a reference package
carries the same weights in the four slots (N3S1). Checks:

- the cooker refuses the N3SI package declared engine 38 or 42 and cooks it
  at 43; it refuses player clips that mix N3S1 and N3SI;
- both readers accept it, and the client's skinned player, combat and skill
  clips equal the reference's (every influence summed) and differ from the
  unchanged fixture's;
- the client refuses N3SI player clips at engine 42 and an N3SI NPC clip at 43.
"""
import json
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools/assetc"))
import main  # noqa: E402
import npc_looks  # noqa: E402
import npc_looks_live  # noqa: E402
from common import digest, string, u  # noqa: E402

OUT = ROOT / "build/check/player-influences"
VERTEX = 64  # p, n, uv (8 f32), joints (4 u32), weights (4 f32)


def player_files(m):
    """The source files of the package's player clips."""
    names = {s for n, s in m["presentation"].items() if n.startswith("player-")}
    names |= {c["source"] for c in m["combat_animation"]["clips"]}
    names |= {"player-skill-%d.bin" % s["animation"] for s in m["skills"]["skills"]}
    return sorted(names)


def rewrite(data, table):
    """`data` (N3S1) with every vertex skinned to joint 1 alone split half to
    joint 1 and half to joint 0: in the influence table (N3SI) when `table`,
    else in the four slots (N3S1). Returns (bytes, vertices changed)."""
    assert data[:4] == b"N3S1", data[:4]
    head, tracks, tail, _ = npc_looks.split_scene(data)
    nv = struct.unpack_from("<I", tail)[0]
    vertices = bytearray(tail[4:4 + nv * VERTEX])
    changed = []
    for v in range(nv):
        at = v * VERTEX
        joints = struct.unpack_from("<4I", vertices, at + 32)
        weights = struct.unpack_from("<4f", vertices, at + 48)
        if joints[0] == 1 and weights == (1.0, 0.0, 0.0, 0.0):
            struct.pack_into("<4I", vertices, at + 32, 1, 0, 0, 0)
            struct.pack_into("<4f", vertices, at + 48, *((0.5, 0, 0, 0) if table else (0.5, 0.5, 0, 0)))
            changed.append(v)
    assert changed, "no joint-1 vertex to split"
    rest = tail[4 + nv * VERTEX:]
    extra = (u(len(changed)) + b"".join(u(v) + u(1) + u(0) + struct.pack("<f", 0.5) for v in changed)) if table else b""
    return (b"N3SI" if table else b"N3S1") + head + tracks + u(nv) + bytes(vertices) + extra + rest, len(changed)


def source(name, table, engine, keep=()):
    """A copy of the fixture source with its player clips rewritten (`table`
    None leaves them; `keep` names files left as they are), declared
    `engine`."""
    root = OUT / name
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(BASE, root)
    m = json.loads((root / "package.json").read_text())
    if table is not None:
        for f in player_files(m):
            if f not in keep:
                data, _ = rewrite((root / f).read_bytes(), table)
                (root / f).write_bytes(data)
    m["engine_version"] = engine
    (root / "package.json").write_text(json.dumps(m))
    return root


def cook(name, table, engine, keep=()):
    root = source(name, table, engine, keep)
    out = OUT / (name + "-package")
    main.cook(root, out)
    return out


def refused(name, table, engine, reason, keep=()):
    root = source(name, table, engine, keep)
    try:
        main.cook(root, OUT / (name + "-package"))
    except ValueError as error:
        assert reason in str(error), (name, error)
    else:
        raise AssertionError("cooker accepted " + name)


def readers(package):
    results = []
    for cmd in [["build/client/n3e-asset-check", str(package)], ["target/debug/n3e-server", "--check-content"]]:
        p = subprocess.run(cmd, env={**os.environ, "N3E_PACKAGE": str(package)}, capture_output=True, text=True)
        results.append((p.returncode, p.stdout + p.stderr))
    return results


def skinned(package, name):
    text = subprocess.check_output(["build/client/n3e-asset-check", str(package), "--scene", name, "0", ".25", ".5",
                                    ".75", "1"], text=True)
    return [list(map(float, line.split()))[1:] for line in text.splitlines()]


def forge(package, change, engine):
    """A copy of `package` with its files changed by `change(files)` and the
    release index rewritten at `engine` (tools/assetc/main.py's layout)."""
    tmp = tempfile.TemporaryDirectory(dir="build")
    out = pathlib.Path(tmp.name) / "release"
    shutil.copytree(package, out)
    files = {p.name: p.read_bytes() for p in out.iterdir() if p.name not in ("release.bin", "release.sha256")}
    change(files)
    m = json.loads(files["recipe.json"])["manifest"]
    for p in out.iterdir():
        p.unlink()
    index = b"N3R1" + u(1) + u(engine) + u(30) + string(m["game_id"]) + string(m["package_version"]) + u(len(files))
    for name, data in sorted(files.items()):
        (out / name).write_bytes(data)
        index += string(name) + u(len(data)) + digest(data)
    (out / "release.bin").write_bytes(index)
    (out / "release.sha256").write_text(digest(index).hex() + "\n")
    return tmp, out


BASE = npc_looks_live.prepare().parent / "source-2"
OUT.mkdir(parents=True, exist_ok=True)
manifest = json.loads((BASE / "package.json").read_text())
assert manifest["engine_version"] == 38, manifest["engine_version"]
files = player_files(manifest)
_, split = rewrite((BASE / files[0]).read_bytes(), True)

# The cooker: N3SI player clips are engine 43, never 38 or 42, and never mixed.
refused("declared-38", True, 38, "incompatible")
refused("declared-42", True, 42, "incompatible")
refused("mixed", True, 43, "player clips mix N3S1 and N3SI", keep=("player-walk.bin",))
package = cook("influences", True, 43)
reference = cook("reference", False, 38)
original = cook("original", None, 38)
clips = [n for n in sorted(os.listdir(package))
         if n.startswith(("player-", "combat-")) and n.endswith(".bin") and n != "combat-animation.bin"]
assert all((package / n).read_bytes()[:4] == b"N3SI" for n in clips), clips
assert all((reference / n).read_bytes()[:4] == b"N3S1" for n in clips), clips
assert all((package / n).read_bytes()[:4] == b"N3S1" for n in os.listdir(package) if n.startswith("npc-") and
           n.endswith(".bin") and n != "npc-looks.bin" and not n.startswith("npc-looks-"))
for p in (package, reference, original):
    assert [code for code, _ in readers(p)] == [0, 0], readers(p)

# The client sums the table: each clip equals the reference's four-slot sum
# and is not the unchanged fixture's.
apart = 0.0
for name in clips:
    drawn, expected, before = skinned(package, name), skinned(reference, name), skinned(original, name)
    assert len(drawn) == 5 and all(len(a) == len(b) for a, b in zip(drawn, expected)), name
    assert max(abs(a - b) for row, ref in zip(drawn, expected) for a, b in zip(row, ref)) < 1e-5, name
    apart = max(apart, max(abs(a - b) for row, old in zip(drawn, before) for a, b in zip(row, old)))
assert apart > 0.01, apart

# The client: N3SI player clips only from engine 43, and never for an NPC clip.
for what, change, engine, why in [
        ("N3SI player clips at engine 42", lambda f: None, 42, "cooked magic/version"),
        ("an N3SI NPC clip", lambda f: f.update({"npc-idle.bin": f["player-idle.bin"]}), 43, "cooked magic/version")]:
    tmp, bad = forge(package, change, engine)
    with tmp:
        code, text = readers(bad)[0]
        assert code != 0 and why in text, (what, text[-300:])

print("PASS player influences (RQ-163): %d player clips with %d split vertices cook as N3SI at engine 43 only "
      "(38 and 42 refused, N3S1/N3SI mixes refused); both readers accept it and the client's skinned clips equal "
      "the four-slot sum (%.3f from the unsplit fixture); the client refuses N3SI player clips at 42 and an N3SI "
      "NPC clip" % (len(clips), split, apart))
