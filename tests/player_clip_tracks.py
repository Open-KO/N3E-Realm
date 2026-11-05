"""RQ-188: track-only player clips (N3ST, engine 46).

A package whose manifest has `"player_clips": "tracks"` keeps player-idle.bin
a whole scene and cooks every other player clip (player-<state>.bin,
combat-<i>.bin, player-skill-<i>.bin) as its track list alone; the client takes
the atlas, skeleton and mesh from player-idle.bin (content/animation.md,
"Track-only player clips").

On the PQ-253 engine 38 fixture (tests/npc_looks_live.py, synthetic). Checks:

- the cooker refuses the package declared engine 38 or 45 and cooks it at 46;
  it refuses another mode and a source clip whose mesh is not player-idle.bin's;
- player-idle.bin is the whole-scene package's byte for byte, and every other
  player clip is N3ST with the whole clip's track bytes; a package without the
  key cooks byte for byte as before (the fixture's own release hash);
- both readers accept it, and the client draws every player clip as the
  whole-scene package does; the same holds with N3SI clips (RQ-163, engine 43
  plus 46);
- the client refuses N3ST at engine 45, as player-idle.bin, as an NPC clip,
  with trailing bytes and with a track past player-idle.bin's nodes.
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

OUT = ROOT / "build/check/player-clip-tracks"
VERTEX = 64  # p, n, uv (8 f32), joints (4 u32), weights (4 f32)


def player_files(m):
    """The source files of the package's player clips."""
    names = {s for n, s in m["presentation"].items() if n.startswith("player-")}
    names |= {c["source"] for c in m["combat_animation"]["clips"]}
    names |= {"player-skill-%d.bin" % s["animation"] for s in m["skills"]["skills"]}
    return sorted(names)


def with_table(data):
    """`data` (N3S1) as N3SI: every vertex skinned to joint 1 alone weighs
    joint 1 at 0.5 in its slots and joint 0 at 0.5 in the influence table
    (tests/player_influences.py's rewrite)."""
    head, tracks, tail, _ = npc_looks.split_scene(data)
    nv = struct.unpack_from("<I", tail)[0]
    vertices = bytearray(tail[4:4 + nv * VERTEX])
    changed = []
    for v in range(nv):
        at = v * VERTEX
        if struct.unpack_from("<I", vertices, at + 32)[0] == 1 and \
                struct.unpack_from("<4f", vertices, at + 48) == (1.0, 0.0, 0.0, 0.0):
            struct.pack_into("<4I", vertices, at + 32, 1, 0, 0, 0)
            struct.pack_into("<4f", vertices, at + 48, 0.5, 0, 0, 0)
            changed.append(v)
    assert changed, "no joint-1 vertex to split"
    table = u(len(changed)) + b"".join(u(v) + u(1) + u(0) + struct.pack("<f", 0.5) for v in changed)
    return b"N3SI" + head + tracks + u(nv) + bytes(vertices) + table + tail[4 + nv * VERTEX:]


def source(name, engine, tracks="tracks", table=False, change=None):
    root = OUT / name
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(BASE, root)
    m = json.loads((root / "package.json").read_text())
    if table:
        for f in player_files(m):
            (root / f).write_bytes(with_table((root / f).read_bytes()))
    if tracks is not None:
        m["player_clips"] = tracks
    m["engine_version"] = engine
    if change:
        change(root, m)
    (root / "package.json").write_text(json.dumps(m))
    return root


def cook(name, engine, **kw):
    out = OUT / (name + "-package")
    main.cook(source(name, engine, **kw), out)
    return out


def refused(name, engine, reason, **kw):
    try:
        main.cook(source(name, engine, **kw), OUT / (name + "-package"))
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
    return subprocess.check_output(["build/client/n3e-asset-check", str(package), "--scene", name, "0", ".25", ".5",
                                    ".75", "1"], text=True)


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


def clip_names(package):
    return sorted(n for n in os.listdir(package) if n.endswith(".bin") and n != "combat-animation.bin"
                  and n.startswith(("player-", "combat-")))


def moved_attachment(root, m):
    """One combat clip source whose attachment node differs from player-idle.bin's."""
    clip = root / m["combat_animation"]["clips"][0]["source"]
    data = bytearray(clip.read_bytes())
    struct.pack_into("<I", data, len(data) - 4, (struct.unpack_from("<I", data, len(data) - 4)[0] + 1) % 2)
    copy = root / "combat-moved.bin"
    copy.write_bytes(bytes(data))
    m["combat_animation"]["clips"][0]["source"] = copy.name


FIXTURE = npc_looks_live.prepare()
BASE = FIXTURE.parent / "source-2"
OUT.mkdir(parents=True, exist_ok=True)
manifest = json.loads((BASE / "package.json").read_text())
assert manifest["engine_version"] == 38, manifest["engine_version"]

# The cooker: N3ST player clips are engine 46 only, in one mode, sharing one mesh.
refused("declared-38", 38, "incompatible")
refused("declared-45", 45, "incompatible")
refused("mode", 46, "player clips mode", tracks="whole")
refused("moved", 46, "differs from player-idle.bin", change=moved_attachment)
package = cook("tracks", 46)
whole = cook("whole", 38, tracks=None)
assert (whole / "release.bin").read_bytes() == (FIXTURE / "release.bin").read_bytes(), "the plain cook moved"

names = clip_names(package)
assert names == clip_names(whole) and "player-idle.bin" in names and any(n.startswith("combat-") for n in names) \
    and any(n.startswith("player-skill-") for n in names), names
assert (package / "player-idle.bin").read_bytes() == (whole / "player-idle.bin").read_bytes()
before = after = 0
for name in names:
    a, b = (package / name).read_bytes(), (whole / name).read_bytes()
    before, after = before + len(b), after + len(a)
    if name != "player-idle.bin":
        assert a == b"N3ST" + npc_looks.split_scene(b)[1], name
for p in (package, whole):
    assert [code for code, _ in readers(p)] == [0, 0], readers(p)
for name in names:
    assert skinned(package, name) == skinned(whole, name), name

# N3SI player clips (RQ-163): the shared tail carries the influence table.
table = cook("tracks-n3si", 46, table=True)
table_whole = cook("whole-n3si", 43, tracks=None, table=True)
assert (table / "player-idle.bin").read_bytes()[:4] == b"N3SI"
assert all((table / n).read_bytes()[:4] == b"N3ST" for n in names if n != "player-idle.bin")
for p in (table, table_whole):
    assert [code for code, _ in readers(p)] == [0, 0], readers(p)
for name in names:
    assert skinned(table, name) == skinned(table_whole, name), name
assert skinned(table, "combat-0.bin") != skinned(package, "combat-0.bin")


def far_node(files):
    data = bytearray(files["combat-0.bin"])
    assert struct.unpack_from("<I", data, 4)[0] > 0, "combat-0.bin has no track"
    struct.pack_into("<I", data, 8, 127)
    files["combat-0.bin"] = bytes(data)


# The client: N3ST only from engine 46, only for a player clip other than
# player-idle.bin, bounded as N3S1's tracks are.
for what, change, engine, why in [
        ("N3ST at engine 45", lambda f: None, 45, "cooked magic/version"),
        ("an N3ST player-idle.bin", lambda f: f.update({"player-idle.bin": f["player-walk.bin"]}), 46,
         "cooked magic/version"),
        ("an N3ST NPC clip", lambda f: f.update({"npc-idle.bin": f["player-walk.bin"]}), 46, "cooked magic/version"),
        ("trailing bytes", lambda f: f.update({"combat-0.bin": f["combat-0.bin"] + b"\0"}), 46,
         "cooked trailing bytes"),
        ("a track past the skeleton", far_node, 46, "animation channel")]:
    tmp, bad = forge(package, change, engine)
    with tmp:
        code, text = readers(bad)[0]
        assert code != 0 and why in text, (what, text[-300:])

print("PASS player clip tracks (RQ-188): %d player clips, %d bytes as whole scenes, %d with N3ST (%.1f%%); "
      "engine 46 only (38 and 45 refused), another mode and a differing mesh refused, the plain cook unchanged; "
      "both readers accept it and the client draws every clip as the whole-scene package does, N3SI too; the "
      "client refuses N3ST at 45, as player-idle.bin, as an NPC clip, with trailing bytes and past the skeleton"
      % (len(names), before, after, 100.0 * after / before))
