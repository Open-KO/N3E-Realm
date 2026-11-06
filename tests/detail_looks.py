"""RQ-221: render detail's looks parts, each player's own face and hair (N3DH flag 8).

KO's world sets a player's face and hair parts by number on its skeleton: the
local player's from the server's MyInfo (1298 005c87c0 stores the face at
+0x7d8 and the hair at +0x7dc, then calls InitFace and InitHair, vtable +0x28
and +0x24, when those parts are empty), another player's from its user-in
(source PlayerOther.cpp: InitFace, and InitHair only without a helmet part).
N3DH's layout flag 8 carries the race's faces and hairs after the appearance
entries: per set a u32 count (0-16) and, when not 0, the body texture slot a
worn key replaces to hide the set and each part's four geometries. On
original synthetic bytes, with no KO data:

- render_detail.serialize writes N3DH with flag 8 when given looks parts (8
  alone, 12 with hidden keys, 9 with render states), the bytes N3D2's plus the
  flags and the two sets; it refuses a set past 16 parts, a slot outside the
  body's textures, a part without four levels or with an empty level 0, and
  looks parts without appearance entries;
- the client's reader (build/client/n3e-asset-check --hidden-detail) reads
  each set's slot and parts, and refuses a count past 16, a slot outside the
  body's textures, an empty level 0, and truncated or trailing bytes;
- a cooked engine 29 package with them is taken by both readers
  (n3e-asset-check reports the sets, n3e-server --check-content the
  projection), and the cook takes layout flags 8 and 12.

The composition (each player's face and hair by its numbers, none past a set
or under a key that replaces its slot) is build/client/n3e-hud-check's
(tests/hud.cpp); the KO cook's sets are tests/ko_player_races.py's.
"""
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools/assetc"))
from item_drops_live import prepare  # noqa: E402
import main  # noqa: E402
import render_detail  # noqa: E402
from common import u  # noqa: E402

CHECK = ROOT / "build/client/n3e-asset-check"


def geometry(slot):
    return ([([x, 0, z], [0, 1, 0], [x, z], [0] * 4, [1, 0, 0, 0], slot) for x, z in [(0, 0), (1, 0), (0, 1)]],
            [0, 1, 2])


# tests/appearance_hides.py's two keys: body slot 1, keys on slot 3.
ARGS = dict(view=[1.134464, .5, 256], thresholds=[[6, 18, 32, 128]] * 4, workload=[30, 60, 100], world_count=1,
            textures=[[(16, 16, bytes([255]) * 1024)]] * 4, radius=1, levels=[geometry(1)] * 4,
            appearances=[([1, 2], [geometry(3)] * 4), ([2], [geometry(3)] * 4)])
STATE = (3, 0.0, 4, 5)


def reader(data, engine=29, keys=2):
    with tempfile.TemporaryDirectory(dir=ROOT / "build") as tmp:
        (Path(tmp) / "render-detail.bin").write_bytes(data)
        return subprocess.run([str(CHECK), "--hidden-detail", tmp, str(engine), str(keys), "0", "0"],
                              capture_output=True, text=True)


def part(slot, triangles=1):
    """A looks part's four levels: `triangles` triangles at level 0, the
    others empty (they draw level 0)."""
    vertices, indices = geometry(slot)
    level0 = (vertices, indices * triangles)
    return [level0, ([], []), ([], []), ([], [])]


# Faces on slot 2 (four, 1..4 triangles), hairs on slot 3 (three, 2 each).
LOOKS = [(2, [part(2, n) for n in range(1, 5)]), (3, [part(3, 2) for _ in range(3)])]


def serializer():
    plain = render_detail.serialize(**ARGS)
    looks = render_detail.serialize(**ARGS, looks=LOOKS)
    assert looks[:4] == b"N3DH" and render_detail.layout(looks[:20]) == 8, looks[:20]
    assert render_detail.valid_layout(8) and render_detail.valid_layout(12) and not render_detail.valid_layout(3)
    assert not render_detail.valid_layout(16) and not render_detail.has_tables(looks[:20])
    # N3D2's bytes, the flags after the projection, then the two sets.
    assert looks[4:16] == plain[4:16] and looks[20:len(plain) + 4] == plain[16:], "N3D2's layout before the sets"
    sets = looks[len(plain) + 4:]
    assert sets[:8] == u(4) + u(2), sets[:8]
    both = render_detail.serialize(**ARGS, hides=[[2], []], looks=LOOKS)
    assert render_detail.layout(both[:20]) == 12 and len(both) == len(looks) + 4 * 2 + 4
    stated = render_detail.serialize(**ARGS, states=[STATE, STATE], looks=LOOKS)
    assert render_detail.layout(stated[:20]) == 9, stated[:20]
    # A race without hair (the Wrinkle Tuarek's): the hair set is a count of 0 alone.
    hairless = render_detail.serialize(**ARGS, looks=[LOOKS[0], (None, [])])
    assert hairless[:len(hairless) - 4] == looks[:len(hairless) - 4] and hairless.endswith(u(0))
    assert looks[len(hairless) - 4:len(hairless) + 4] == u(3) + u(3)
    refused = 0
    for name, bad, why in [
        ("17 faces", [(2, [part(2)] * 17), (3, [])], "looks part count"),
        ("a world slot", [(0, [part(0)]), (None, [])], "looks slot"),
        ("a slot past the textures", [(4, [part(2)]), (None, [])], "looks slot"),
        ("no slot", [(None, [part(2)]), (None, [])], "looks slot"),
        ("three levels", [(2, [part(2)[:3]]), (None, [])], "looks part levels"),
        ("an empty level 0", [(2, [[([], [])] * 4]), (None, [])], "looks part levels"),
        ("one set", [(2, [part(2)])], "looks sets"),
    ]:
        try:
            render_detail.serialize(**ARGS, looks=bad)
        except ValueError as error:
            assert why in str(error), (name, error)
            refused += 1
        else:
            raise AssertionError("serialized %s" % name)
    try:
        render_detail.serialize(**dict(ARGS, appearances=()), looks=LOOKS)
    except ValueError as error:
        assert "need appearance entries" in str(error), error
        refused += 1
    else:
        raise AssertionError("looks parts without appearance entries")
    print("PASS N3DH looks serializer: flag 8 (12 with hidden keys, 9 with states), N3D2's bytes plus the faces and "
          "hairs; %d malformed sets refused (17 parts, world or missing slot, slot past the textures, no slot, three "
          "levels, empty level 0, one set, no appearance entries)" % refused, flush=True)
    return looks, len(plain) + 4


def client_reader(looks, at):
    good = reader(looks)
    assert good.returncode == 0, (good.stdout, good.stderr)
    assert good.stdout.splitlines() == ["key=1 hides=", "key=2 hides=", "faces slot=2 parts=3,6,9,12",
                                        "hairs slot=3 parts=6,6,6"], good.stdout
    both = render_detail.serialize(**ARGS, hides=[[2], []], looks=LOOKS)
    assert reader(both).stdout.splitlines()[:3] == ["key=1 hides=2", "key=2 hides=", "faces slot=2 parts=3,6,9,12"]
    hairless = render_detail.serialize(**ARGS, looks=[LOOKS[0], (None, [])])
    assert reader(hairless).stdout.splitlines()[-1] == "faces slot=2 parts=3,6,9,12", reader(hairless).stdout

    def count(value):
        return looks[:at] + u(value) + looks[at + 4:]

    def slot(value):
        return looks[:at + 4] + u(value) + looks[at + 8:]

    cases = [
        ("17 faces", count(17), ""),
        ("a world slot", slot(0), "looks slot"),
        ("a slot past the textures", slot(4), "looks slot"),
        ("an empty level 0", render_detail.serialize(**ARGS, looks=[(2, [part(2)]), (None, [])])[:at + 8] + u(0) + u(0)
         + b"".join(u(0) * 2 for _ in range(3)) + u(0), "empty looks part"),
        ("no sets", looks[:at], ""),
        ("truncated", looks[:-1], ""),
        ("trailing", looks + b"\0", ""),
    ]
    refused = 0
    for name, data, why in cases:
        p = reader(data)
        assert p.returncode != 0 and why in p.stdout + p.stderr, (name, p.stdout[-300:], p.stderr[-300:])
        refused += 1
    print("PASS N3DH looks client reader: each set's slot and parts read, with or without hidden keys and with no "
          "hairs; %d malformed files refused (17 parts, world slot, slot past the textures, empty level 0, missing "
          "sets, truncated, trailing)" % refused, flush=True)


def package(looks):
    base = prepare(full=True)
    with tempfile.TemporaryDirectory(dir=ROOT / "build") as tmp:
        root, out = Path(tmp) / "source", Path(tmp) / "package"
        shutil.copytree(base.parent / "source", root)
        m = json.loads((root / "package.json").read_text())
        blade, shield = (next(i for i in m["equipment"]["items"] if i["id"] == name)
                         for name in ("demo:item/blade", "demo:item/shield"))
        m.update(engine_version=29, protocol_version=22, world="map.bin", render_detail="detail.bin",
                 exploration=dict(turbo_multiplier=10, fog_start=192, fog_end=256, fog_color=[.6, .7, .8],
                                  lod="lod.bin"),
                 appearance=[dict(item=blade["id"], slot=0), dict(item=shield["id"], slot=1)])
        vs = [[0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0], [4, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0],
              [0, 0, 4, 0, 1, 0, 0, 1, 0, 0, 0, 0]]
        (root / "map.bin").write_bytes(b"N3W1" + u(16) + u(16) + u(8) + u(1) + bytes([255]) * 1024 + u(3)
                                       + b"".join(struct.pack("<12f", *v) for v in vs) + u(3) + u(0) + u(1) + u(2))
        (root / "lod.bin").write_bytes(b"N3L2" + u(1) + struct.pack("<5f", 2, 0, 2, 4, 1) + u(0) + u(1)
                                       + struct.pack("<f", 0) + u(3) + u(0) + u(1) + u(2))
        for data in (looks, render_detail.serialize(**ARGS, hides=[[2], []], looks=LOOKS)):
            (root / "detail.bin").write_bytes(data)
            (root / "package.json").write_text(json.dumps(m))
            main.cook(root, out)
            assert (out / "render-detail.bin").read_bytes() == data
            env = {**os.environ, "N3E_PACKAGE": str(out)}
            client = subprocess.run([str(CHECK), str(out)], env=env, capture_output=True, text=True)
            server = subprocess.run(["target/debug/n3e-server", "--check-content"], env=env, capture_output=True,
                                    text=True)
            assert client.returncode == 0 and server.returncode == 0, (client.stderr[-400:], server.stderr[-400:])
            assert "detail looks faces=4 face_slot=2 hairs=3 hair_slot=3" in client.stdout.splitlines(), client.stdout
            assert server.stdout.splitlines()[0] in client.stdout.splitlines()
    print("PASS N3DH looks package: both readers take an engine 29 package with faces and hairs (flags 8 and 12), "
          "the client reports the sets", flush=True)


looks, at = serializer()
client_reader(looks, at)
package(looks)
