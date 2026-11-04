"""RQ-164: render detail past four joint influences (N3DI / N3DJ, engine 44).

A KO body or appearance part whose skin has drawn vertices with more than four
joint influences (the Arch Tuarek's lower part: 49 with five) keeps every
influence in `render-detail.bin`, as KO's skinning 00419f00 sums them (PQ-283,
D-176; RQ-163 for the player clips). N3DI is N3D2 and N3DJ is N3D3 with
D-176's influence table between each geometry's vertices and its indices; a
package with one is engine 44 (content/appearance.md, "Influence tables in
render detail").

On the PQ-253 engine 38 fixture (tests/npc_looks_live.py, synthetic) the
render detail is replaced by synthetic geometry on the player skeleton's
joints 0 and 1: a level-0 and an appearance triangle whose corners weigh
joint 1 at 0.5 in their four slots and joint 0 at 0.5 as a fifth influence,
and a reference with the same weights in the four slots. Checks:

- render_detail.serialize: a fifth influence is refused without `influences`;
  with it and no weight past the slots the bytes are N3D2's; N3DI / N3DJ add
  only the tables (every geometry, count 0 where none); tables without
  appearance entries are refused;
- the cooker refuses N3DI declared 38 or 43 and cooks it at 44, N3DJ too,
  and refuses N3DI in an engine 37 package;
- both readers accept them; the client's detail geometries skinned on the
  attack clip equal the reference's (every influence summed) and level 0 and
  the entry's level 0 differ from the one-joint version;
- both readers refuse N3DI at engine 43; the client refuses a table out of
  order, past the skeleton, with a zero weight or with weights that do not
  sum to 1.
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
import npc_looks_live  # noqa: E402
import npc_templates_live  # noqa: E402
from common import digest, string, u  # noqa: E402
import importlib.util  # noqa: E402

# By path: tests/render_detail.py (a check) shares the cooker module's name.
_spec = importlib.util.spec_from_file_location("render_detail", ROOT / "tools/assetc/render_detail.py")
render_detail = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(render_detail)

OUT = ROOT / "build/check/detail-influences"
CORNERS = [(0, 0), (1, 0), (0, 1)]


def triangle(slot, kind):
    """A triangle on joints 0 and 1: `kind` "table" weighs joint 1 0.5 in the
    slots and joint 0 0.5 as a fifth influence; "slots" the same pair in the
    slots; "zero" a fifth influence of weight 0; "one" joint 1 alone."""
    joints, weights = {
        "table": ([1, 0, 0, 0, 0], [.5, 0, 0, 0, .5]),
        "slots": ([1, 0, 0, 0], [.5, .5, 0, 0]),
        "zero": ([1, 0, 0, 0, 0], [1, 0, 0, 0, 0]),
        "one": ([1, 0, 0, 0], [1, 0, 0, 0]),
        "half": ([1, 0, 0, 0], [.5, 0, 0, 0]),  # the table's slots alone (a layout check only)
    }[kind]
    return ([([x, 1, z], [0, 1, 0], [x, z], list(joints), list(weights), slot) for x, z in CORNERS], [0, 1, 2])


def args(kind, appearance_kind=None):
    """serialize's arguments: level 0 of `kind` (levels 1-3 joint 1 alone)
    and one appearance entry whose level 0 is `appearance_kind` (default `kind`)."""
    a = appearance_kind or kind
    return dict(view=[1.134464, .5, 256], thresholds=[[6, 18, 32, 128]] * 4, workload=[30, 60, 100],
                world_count=1, textures=[[(16, 16, bytes([255]) * 1024)]] * 3, radius=1,
                levels=[triangle(1, kind)] + [triangle(1, "one")] * 3,
                appearances=[([1], [triangle(2, a)] + [triangle(2, "one")] * 3)])


def refuses(call, reason):
    try:
        call()
    except ValueError as error:
        assert reason in str(error), (reason, error)
    else:
        raise AssertionError("accepted: " + reason)


STATE = (3, 0.0, 4, 5)

# The serializer.
plain = render_detail.serialize(**args("slots"))
assert plain[:4] == b"N3D2"
refuses(lambda: render_detail.serialize(**args("table")), "past four joint influences")
refuses(lambda: render_detail.serialize(**args("zero")), "past four joint influences")
one = render_detail.serialize(**args("one"))
assert render_detail.serialize(**args("zero"), influences=True) == one, "no further weight keeps the N3D2 bytes"
assert render_detail.serialize(**args("slots"), influences=True) == plain, "four slots keep the N3D2 bytes"
n3di = render_detail.serialize(**args("table"), influences=True)
n3dj = render_detail.serialize(**args("table"), influences=True, states=[STATE])
assert n3di[:4] == b"N3DI" and n3dj[:4] == b"N3DJ", (n3di[:4], n3dj[:4])
half = render_detail.serialize(**args("half"))
table = u(3) + b"".join(u(v) + u(1) + u(0) + struct.pack("<f", .5) for v in range(3))
# N3DI is N3D2 (here with the table's slot weights) with a table between every
# geometry's vertices and indices: the table where level 0 and the entry's
# level 0 have one, a count of 0 elsewhere.
head = 4 + 12 + 64 + 12 + 4 + 4 + 3 * (4 + 8 + 1024) + 4 + 4  # to the first level
vertices, indices = 8 + 3 * 68, 3 * 4  # a vertex: 8 f32, 4 joints, 4 weights, a slot
pieces, at = [b"N3DI" + half[4:head]], head
for g in range(8):
    if g == 4:  # after the four levels: no attachments, one entry replacing slot 1
        pieces.append(half[at:at + 16])
        at += 16
    pieces.append(half[at:at + vertices])
    pieces.append(table if g in (0, 4) else u(0))
    pieces.append(half[at + vertices:at + vertices + indices])
    at += vertices + indices
assert at == len(half), (at, len(half))
expected = b"".join(pieces)
assert n3di == expected, "N3DI is N3D2 with the tables"
assert n3dj == n3di.replace(b"N3DI", b"N3DJ", 1) + u(3) + struct.pack("<f", 0) + u(4) + u(5), "N3DJ is N3DI plus the states"
refuses(lambda: render_detail.serialize(**{**args("table"), "appearances": ()}, influences=True),
        "need appearance entries")
many = triangle(1, "one")
many = ([(p, n, uv, [1] + [0] * 64, [.5] + [0] * 3 + [.5 / 61] * 61, s) for p, n, uv, _, _, s in many[0]], many[1])
refuses(lambda: render_detail.serialize(**{**args("one"), "levels": [many] * 4}, influences=True),
        "past 64 joint influences")


def source(name, kind, engine, base, states=None):
    """A copy of `base` whose detail.bin is args(kind), declared `engine`."""
    root = OUT / name
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(base, root)
    m = json.loads((root / "package.json").read_text())
    (root / m["render_detail"]).write_bytes(render_detail.serialize(**args(kind), influences=True, states=states))
    m["engine_version"] = engine
    (root / "package.json").write_text(json.dumps(m))
    return root


def cook(name, kind, engine, base, states=None):
    out = OUT / (name + "-package")
    main.cook(source(name, kind, engine, base, states), out)
    return out


def refused(name, kind, engine, base, reason, states=None):
    root = source(name, kind, engine, base, states)
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


def skinned(package):
    text = subprocess.check_output(["build/client/n3e-asset-check", str(package), "--detail", "player-attack.bin", "0", ".25", ".5",
                                    ".75", "1"], text=True)
    return [(line.split()[0], line.split()[1], list(map(float, line.split()[2:]))) for line in text.splitlines()]


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
OLD = npc_templates_live.prepare().parent / "source"
OUT.mkdir(parents=True, exist_ok=True)
assert json.loads((BASE / "package.json").read_text())["engine_version"] == 38
assert json.loads((OLD / "package.json").read_text())["engine_version"] == 37

# The cooker: N3DI / N3DJ are engine 44, never 38 or 43, and need an engine 38+ package.
refused("declared-38", "table", 38, BASE, "incompatible")
refused("declared-43", "table", 43, BASE, "incompatible")
refused("engine-37", "table", 37, OLD, "needs an engine 38+ package")
package = cook("influences", "table", 44, BASE)
states = cook("states", "table", 44, BASE, states=[STATE])
reference = cook("reference", "slots", 38, BASE)
original = cook("original", "one", 38, BASE)
assert (package / "render-detail.bin").read_bytes()[:4] == b"N3DI"
assert (states / "render-detail.bin").read_bytes()[:4] == b"N3DJ"
assert (reference / "render-detail.bin").read_bytes()[:4] == b"N3D2"
for p in (package, states, reference, original):
    assert [code for code, _ in readers(p)] == [0, 0], (p, readers(p))

# The client sums the table: every geometry equals the reference's four-slot
# sum and level 0 and the entry's level 0 are not the one-joint version's.
drawn, expected_rows, before = skinned(package), skinned(reference), skinned(original)
assert skinned(states) == drawn
assert [r[:2] for r in drawn] == [r[:2] for r in expected_rows] and len(drawn) == 5 * 8, len(drawn)
assert max(abs(a - b) for (_, _, row), (_, _, ref) in zip(drawn, expected_rows) for a, b in zip(row, ref)) < 1e-5
apart = {}
for (_, label, row), (_, _, old) in zip(drawn, before):
    apart[label] = max(apart.get(label, 0.0), max(abs(a - b) for a, b in zip(row, old)))
moved = {label for label, d in apart.items() if d > 0.01}
assert moved == {"level0", "appearance1-0"}, apart

# The client: N3DI / N3DJ only from engine 44, and their tables checked.
data = (package / "render-detail.bin").read_bytes()
first_table = data.index(table)


def patched(offset, value, fmt="<I"):
    out = bytearray(data)
    struct.pack_into(fmt, out, first_table + offset, value)
    return bytes(out)


for what, change, engine, why in [
        ("N3DI at engine 43", lambda f: None, 43, "cooked magic/version"),
        ("vertices out of order", lambda f: f.update({"render-detail.bin": patched(20, 0)}), 44,
         "detail influence vertex"),
        ("a joint past the skeleton", lambda f: f.update({"render-detail.bin": patched(12, 4096)}), 44,
         "detail influence joint"),
        ("a zero weight", lambda f: f.update({"render-detail.bin": patched(16, 0.0, "<f")}), 44,
         "detail influence weight"),
        ("weights off 1", lambda f: f.update({"render-detail.bin": patched(16, .25, "<f")}), 44,
         "detail weight sum")]:
    tmp, bad = forge(package, change, engine)
    with tmp:
        (code, text), (server, server_text) = readers(bad)
        assert code != 0 and why in text, (what, text[-300:])
        if engine == 43:  # the server checks the magic against the engine too
            assert server != 0 and "render detail magic" in server_text, (what, server_text[-300:])

print("PASS detail influences (RQ-164): render detail with a fifth influence cooks as N3DI / N3DJ at engine 44 only "
      "(38 and 43 refused, an engine 37 package refused), N3D2 bytes kept without further weight; both readers "
      "accept it and the client's skinned levels and appearance meshes equal the four-slot sum (%.3f from the "
      "one-joint version); both readers refuse N3DI at 43 and the client bad tables" % max(apart.values()))
