"""PQ-254: KO NPC models from NPC_Looks rows (tools/assetc/ko_npc_looks.py), on
an original synthetic client tree (tools/assetc/ko_npc_looks_fixture.py). No KO
data, no containers.

Checks the row rules read in the client binary (docstring of ko_npc_looks):
a row without a column 16 character file builds from columns 3, 4 and parts
5-10 and never reads columns 11-15 or 17; a row with one loads the .n3chr,
replaces its part i by a non-empty column 5 + i only below its part count and
never reads columns 3, 4 or 11-15 (each of those columns names an absent file
here, so reading one would fail the row);
the clips are 0, 2, 4 and 10, and one that starts and ends on one frame
converts as a held pose (PQ-273); a table without clips converts every state
as the joints at frame 0 held, on both row paths and on a skeleton without
keys, a table of one or two clips gives the missing states its clip 0, and a
table that has the walk clip but lacks another is refused (PQ-268, D-178);
column 36 is the name flag; entries are ordered by resource ID. Every failing row fails closed with the file and reason, and
a zone with any failed key is refused. The converted entries cook into an
engine 38 package that both readers accept.

(Named *_import so `import ko_npc_looks` never finds this file.)
"""
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path("tools/assetc").resolve()))
sys.path.append(str(Path("tests").resolve()))
import ko_character  # noqa: E402
import ko_npc_looks  # noqa: E402
import ko_npc_looks_fixture as fixture  # noqa: E402
import npc_looks  # noqa: E402


def refused(fn, *phrases):
    try:
        fn()
    except ValueError as error:
        assert all(p in str(error) for p in phrases), (phrases, str(error))
        return str(error)
    raise AssertionError("accepted: %r" % (phrases,))


ROWS = [
    # Character file path: the .n3chr's parts are [blue, green]; column 5 puts red at
    # position 0, column 6 is empty (green stays), columns 7 and 8 name positions 2 and
    # 3, past the two parts (absent files, never read). Columns 3, 4 and 11-15 name
    # absent files too.
    fixture.row(200, c3="chr/absent.n3joint", c4="chr/absent.n3anim", c5="item/red.n3cpart",
                c7="item/absent.n3cpart", c8="item/absent3.n3cpart", c16="chr/b.n3chr",
                **{"c%d" % c: "item/absent%d.n3cpart" % c for c in range(11, 16)}),
    # Row path: parts at positions 0 and 2; columns 11-15 and 17 name absent files,
    # never read; column 35 = 0 (fixed facing), column 36 = 1.
    fixture.row(300, c3="chr/a.n3joint", c4="chr/a.n3anim", c5="item/red.n3cpart", c7="item/green.n3cpart",
                c17="chr/absent.n3fxplug", c35=0, c36=1,
                **{"c%d" % c: "item/absent%d.n3cpart" % c for c in range(11, 16)}),
    # Row path on a clip table whose clips 4-9 start and end on frame 2.5 (PQ-273:
    # KO's shop and smith attack clips); clip 4 converts as a held pose.
    fixture.row(350, c3="chr/a.n3joint", c4="chr/held.n3anim", c5="item/blue.n3cpart"),
    fixture.row(400, c3="chr/a.n3joint", c4="chr/a.n3anim", c5="item/missing.n3cpart"),
    fixture.row(500, c3="chr/a.n3joint", c4="chr/short.n3anim", c5="item/red.n3cpart"),
    # PQ-268: tables of one and two clips (KO's 24000 and 14001), and a table
    # without clips on the row path (the crystals and bind point, on a skeleton
    # whose keys start at 0.3 rad) and on the .n3chr path (the guard stones, on a
    # skeleton without keys).
    fixture.row(520, c3="chr/a.n3joint", c4="chr/one.n3anim", c5="item/red.n3cpart"),
    fixture.row(530, c3="chr/a.n3joint", c4="chr/two.n3anim", c5="item/green.n3cpart"),
    fixture.row(600, c3="chr/broken.n3joint", c4="chr/a.n3anim", c5="item/red.n3cpart"),
    fixture.row(650, c3="chr/rest.n3joint", c4="chr/none.n3anim", c5="item/red.n3cpart"),
    fixture.row(660, c3="chr/a.n3joint", c4="chr/a.n3anim"),
    fixture.row(670, c3="chr/absent.n3joint", c4="chr/absent.n3anim", c16="chr/c.n3chr"),
]
OUT = Path("build/pq254/check")
if OUT.exists():
    shutil.rmtree(OUT)
client = OUT / "client"
fixture.write(client, ROWS)
keys = ["demo:looks/%d" % pid for pid in (300, 200, 350, 400, 500, 520, 530, 600, 650, 660, 670, 700, 300)]
entries, failures, report = ko_npc_looks.convert(client, keys, OUT / "root", "demo", OUT / "work")

# Order: by resource ID (entry 0 is the lowest, KO's fallback node by inference, PQ-253).
assert [e["key"] for e in entries] == ["demo:looks/%d" % pid for pid in (200, 300, 350, 520, 530, 650, 670)], [
    e["key"] for e in entries]
assert [e["name_always"] for e in entries] == [False, True, False, False, False, False, False]
# Clips 0, 2, 4 and 10 of the table: clip i lasts (1 + i) / 10 s.
for e in entries[:2]:
    assert [round(c["duration"], 4) for c in e["clips"]] == [0.1, 0.3, 0.5, 1.1], e["clips"]
    assert [c["loop_blend"] for c in e["clips"]] == [True, True, False, False], e["clips"]
assert report["demo:looks/300"]["clips"] == dict(idle=0, walk=2, attack=4, death=10)


def atlas(entry):
    """The set of texel colours in the entry's idle clip atlas."""
    head = npc_looks.split_scene((OUT / "root" / entry["clips"][0]["source"]).read_bytes())[0]
    w, h = int.from_bytes(head[0:4], "little"), int.from_bytes(head[4:8], "little")
    pixels = head[8:8 + w * h * 3]
    return {pixels[i:i + 3] for i in range(0, len(pixels), 3)}


chr_entry, row_entry, held_entry, one_entry, two_entry, rest_entry, still_entry = entries
# Character path: the row's red replaced the .n3chr's blue at position 0, green kept.
assert atlas(chr_entry) == {fixture.RGB["red"], fixture.RGB["green"]}, atlas(chr_entry)
assert report["demo:looks/200"]["definition"]["parts"] == ["item/red.n3cpart", "item/green.n3cpart"]
assert report["demo:looks/200"]["definition"]["joint"] == "chr/a.n3joint"
assert report["demo:looks/200"]["omitted"] == ["character extras chr/b.n3fxplug"], report["demo:looks/200"]
# Row path: positions 0 and 2 (red, green); columns 11 and 17 never read.
assert atlas(row_entry) == {fixture.RGB["red"], fixture.RGB["green"]}
assert report["demo:looks/300"]["definition"]["parts"] == ["item/red.n3cpart", "item/green.n3cpart"]
assert report["demo:looks/300"]["omitted"] == ["effects chr/absent.n3fxplug", "fixed facing (column 35 = 0)"]
assert report["demo:looks/300"]["vertices"] == 6
assert not any("absent" in s for r in report.values() for s in r["sources"]), [r["sources"] for r in report.values()]
# PQ-273: the held attack clip (frames 2.5 .. 2.5) lasts one 60 Hz sample with its
# strike marker at 0; the other three clips of that row are as above. Its track holds
# the joint's frame-2.5 pose (keys 2 and 3 of the fixture's turn about y, half way:
# 0.025 rad) at both keys, independent of the converter's sampler.
assert [round(c["duration"], 4) for c in held_entry["clips"]] == [0.1, 0.3, 0.0167, 1.1], held_entry["clips"]
assert abs(held_entry["clips"][2]["duration"] - 1 / 60) < 1e-9
assert held_entry["clips"][2]["markers"] == [0.0, -1], held_entry["clips"][2]
assert held_entry["clips"][2]["loop_blend"] is False
assert report["demo:looks/350"]["clips"] == dict(idle=0, walk=2, attack=4, death=10)
attack = json.loads((OUT / "work/350/attack/character.gltf").read_text())
attack_bin = (OUT / "work/350/attack/character.bin").read_bytes()


def floats(accessor, width):
    a = attack["accessors"][accessor]
    view = attack["bufferViews"][a["bufferView"]]
    return [list(struct.unpack_from("<%df" % width, attack_bin, view["byteOffset"] + 4 * width * i))
            for i in range(a["count"])]


(sampler,) = attack["animations"][0]["samplers"]
times, keys_q = floats(sampler["input"], 1), floats(sampler["output"], 4)
assert [round(t[0], 7) for t in times] == [0.0, round(1 / 60, 7)], times
expected_q = [0.0, -math.sin(0.025), 0.0, math.cos(0.025)]  # converted basis (-x, -y, z, w)
for q in keys_q:
    assert max(abs(a - b) for a, b in zip(q, expected_q)) < 1e-6, (keys_q, expected_q)
provenance = json.loads((OUT / "work/350/attack/provenance.json").read_text())
assert provenance["held_frame"] == 2.5 and provenance["selected_clip"] == 4, provenance
assert not any("held_frame" in json.loads((OUT / "work/350" / s / "provenance.json").read_text())
               for s in ("idle", "walk", "death"))
print("PASS NPC_Looks rows convert as the client builds them: .n3chr with row parts below its part count "
      "(3, 4, 11-15 never read), columns 3/4/5-10 otherwise (11-15, 17 never read), clips 0/2/4/10, name flag, "
      "resource-ID order")

# PQ-268 (D-178): KO's clip starts leave the clip already playing for an index
# at or past the table's count. A table of one or two clips: every missing state
# takes clip 0 (its 0.1 s), byte for byte; attack and death do not loop.
for entry, count in ((one_entry, 1), (two_entry, 2)):
    pid = entry["key"].split("/")[1]
    assert [round(c["duration"], 4) for c in entry["clips"]] == [0.1] * 4, entry["clips"]
    assert [c["loop_blend"] for c in entry["clips"]] == [True, True, False, False], entry["clips"]
    assert [round(c["blend"], 6) for c in entry["clips"]] == [0.2] * 4, entry["clips"]
    sources = {(OUT / "root" / c["source"]).read_bytes() for c in entry["clips"]}
    assert len(sources) == 1, entry["key"]
    assert report[entry["key"]]["clips"] == dict(idle=0, walk=0, attack=0, death=0)
    assert report[entry["key"]]["omitted"] == [
        "walk clip 2, attack clip 4, death clip 10 past the table's %d clips: the idle clip 0" % count]
    assert all(json.loads((OUT / "work" / pid / s / "provenance.json").read_text())["selected_clip"] == 0
               for s in ("idle", "walk", "attack", "death"))
# A table without clips: every state is the joints at frame 0 held (two keys
# 1/60 s apart, no blend, no loop, no marker), on the row path (keys from
# 0.3 rad: the pose is key 0, not the base rotation) and the .n3chr path (no
# keys: the base rotation, 0.2 rad, written as a held track).
for entry, angle in ((rest_entry, 0.3), (still_entry, 0.2)):
    pid = entry["key"].split("/")[1]
    assert [(c["duration"], c["blend"], c["loop_blend"], c["markers"]) for c in entry["clips"]] == [
        (1 / 60, 0.0, False, [-1, -1])] * 4, entry["clips"]
    assert report[entry["key"]]["clips"] == dict(idle=None, walk=None, attack=None, death=None)
    assert report[entry["key"]]["omitted"][-1] == "no clips: every state the joints at frame 0", report[entry["key"]]
    for state in ("idle", "walk", "attack", "death"):
        work = OUT / "work" / pid / state
        gltf = json.loads((work / "character.gltf").read_text())
        data = (work / "character.bin").read_bytes()

        def values(accessor, width):
            a = gltf["accessors"][accessor]
            view = gltf["bufferViews"][a["bufferView"]]
            return [list(struct.unpack_from("<%df" % width, data, view["byteOffset"] + 4 * width * i))
                    for i in range(a["count"])]

        (sampler,) = gltf["animations"][0]["samplers"]
        assert [c["target"]["path"] for c in gltf["animations"][0]["channels"]] == ["rotation"]
        assert [round(t[0], 7) for t in values(sampler["input"], 1)] == [0.0, round(1 / 60, 7)]
        expected_q = [0.0, -math.sin(angle), 0.0, math.cos(angle)]  # converted basis (-x, -y, z, w)
        for q in values(sampler["output"], 4):
            assert max(abs(a - b) for a, b in zip(q, expected_q)) < 1e-6, (pid, state, q, expected_q)
        provenance = json.loads((work / "provenance.json").read_text())
        assert provenance["selected_clip"] is None and provenance["held_frame"] == 0.0, provenance
        assert provenance["rest_pose"] == ko_character.REST_CLIP and provenance["animations"] == []
assert report["demo:looks/670"]["definition"]["joint"] == "chr/still.n3joint"
assert not any("rest_pose" in json.loads((OUT / "work" / str(pid) / s / "provenance.json").read_text())
               for pid in (200, 300, 350, 520, 530) for s in ("idle", "walk", "attack", "death"))
# The plan for every table size: none (rest), one or two (clip 0), three to ten
# (refused: the clip KO keeps depends on the state before), eleven (as named).
assert ko_npc_looks.clip_plan(0)[0] == [("idle", None), ("walk", None), ("attack", None), ("death", None)]
for count in (1, 2):
    assert ko_npc_looks.clip_plan(count)[0] == [("idle", 0), ("walk", 0), ("attack", 0), ("death", 0)]
for count in range(3, 11):
    refused(lambda count=count: ko_npc_looks.clip_plan(count), "past the table's %d clips" % count,
            "depends on the state before", "attack clip 4" if count <= 4 else "death clip 10")
assert ko_npc_looks.clip_plan(11) == (list(ko_npc_looks.CLIPS), None)
# The converter: the rest pose only for a table without clips; an index on such
# a table stays refused (the player path).
refused(lambda: ko_character.convert(client, ko_npc_looks.SOURCE, OUT / "work4", None, definition=dict(
    report["demo:looks/300"]["definition"]), player=False), "rest pose asked for a table of 11 clips")
refused(lambda: ko_character.convert(client, ko_npc_looks.SOURCE, OUT / "work4", 0, definition=dict(
    report["demo:looks/650"]["definition"]), player=False), "animation table has no clips")
print("PASS clip indices past the table (PQ-268): no clips converts every state as the joints at frame 0 held "
      "(row and .n3chr paths, keyed and keyless skeletons), one or two clips give the missing states clip 0, "
      "three to ten are refused")

# Fail closed per row, naming the file and the reason.
expected = {
    "demo:looks/400": ("item/missing.n3cpart", "missing/ambiguous KO dependency"),
    "demo:looks/500": ("death clip 10", "chr/short.n3anim", "past the table's 5 clips", "depends on the state before"),
    "demo:looks/600": ("chr/broken.n3joint", "truncated KO data"),
    "demo:looks/660": ("no parts",),
    "demo:looks/700": ("no NPC_Looks row",),
}
assert set(failures) == set(expected), failures
for key, phrases in expected.items():
    assert all(p in failures[key] for p in phrases), (key, failures[key])
# A failed row leaves nothing under the package root.
assert sorted(p.name for p in (OUT / "root/npc-looks-src").iterdir()) == sorted(
    "%d-%s.bin" % (pid, s) for pid in (200, 300, 350, 520, 530, 650, 670) for s in ("idle", "walk", "attack", "death"))
templates = [dict(looks=k) for k in keys]
message = refused(lambda: ko_npc_looks.cook(client, templates, OUT / "root2", "demo", OUT / "work2"),
                  "NPC looks not converted", *expected)
refused(lambda: ko_npc_looks.convert(client, ["demo:looks/x"], OUT / "root3", "demo", OUT / "work3"),
        "not demo:looks/<resource id>")
refused(lambda: ko_npc_looks.convert(client, ["other:looks/1"], OUT / "root3", "demo", OUT / "work3"),
        "not demo:looks/<resource id>")
# NPC-in sign-extends the record's resource ID (005cd68f): 32768 never matches.
refused(lambda: ko_npc_looks.convert(client, ["demo:looks/32768"], OUT / "root3", "demo", OUT / "work3"),
        "not demo:looks/<resource id>")
print("PASS failing rows fail closed with the file and reason (missing part, a table of five clips, truncated "
      "skeleton, no parts, no row) and a zone with any failure is refused")

# The table's layout: header types, repeated ids, malformed rows and flags.
good = (client / "Data/NPC_Looks.tbl.csv").read_bytes()
lines = good.decode("utf-8-sig").splitlines()
bad = {
    "header": "\n".join([lines[0].replace("Int32", "Int16", 1)] + lines[1:]),
    "repeated": "\n".join(lines + [lines[1]]),
    "short row": "\n".join(lines[:1] + [lines[1].rsplit(",", 1)[0]]),
    "name flag": "\n".join(lines[:1] + [lines[1][:lines[1].rfind('"0","100"')] + '"2","100","100"']),
    "id past 32767": "\n".join(lines[:1] + ['"32768"' + lines[1][lines[1].index(","):]]),
}
for why, text in bad.items():
    refused(lambda text=text: ko_npc_looks.table(text.encode()), "NPC_Looks")
assert sorted(ko_npc_looks.table(good)) == [200, 300, 350, 400, 500, 520, 530, 600, 650, 660, 670]
print("PASS NPC_Looks table refuses another header, a repeated resource ID, a short row, a name flag "
      "outside 0/1 and a resource ID past 32767")

# The converted entries (the rest poses and reused clips of PQ-268 among them)
# cook into an engine 38 package both readers accept.
from npc_templates_live import prepare as base  # noqa: E402
import main  # noqa: E402
import npc_looks_live  # noqa: E402

source, root, package = base().parent / "source", OUT / "package-source", OUT / "package"
shutil.copytree(source, root)
shutil.copytree(OUT / "root/npc-looks-src", root / "npc-looks-src")
m = json.loads((root / "package.json").read_text())
templates = [dict(npc_looks_live.BASE, name="demo:creature/t%d" % i, looks=e["key"]) for i, e in enumerate(entries)]
spawns = (npc_looks_live.SPAWNS + [[-8.0 + 1.5 * i, -12.0] for i in range(6)])[:len(entries)]
m["gameplay"].update(spawns=spawns, spawn_x=npc_looks_live.PLAYER[0], spawn_z=npc_looks_live.PLAYER[1])
m["npc"]["templates"] = templates
m["npc"]["slots"] = [dict(area=[0, 0, 0, 0], respawn_ticks=60, template=t["name"]) for t in templates]
m["editing"]["spawns"] = list(range(len(entries)))
m["npc_looks"] = entries
m.update(engine_version=38, protocol_version=30)
(root / "package.json").write_text(json.dumps(m))
main.cook(root, package)
lines = npc_looks_live.check_readers(package.resolve())
measured = next(line for line in lines if line.startswith("npc looks "))
assert measured.startswith("npc looks 7 "), measured
print("PASS converted looks cook into an engine 38 package both readers accept (%s)" % measured)

# PQ-265 (D-173): a row whose parts carry render states (a double-sided part
# on a see-through DXT1, then a blended, unlit part on a DXT3 after an opaque
# one) converts into N3SM clips with the parts' runs in order, and the entry
# cooks into an N3MM model in an engine 39 package both readers accept.

client2, out2 = OUT / "client-materials", OUT / "materials"
fixture.write(client2, ROWS + [fixture.row(800, c3="chr/a.n3joint", c4="chr/a.n3anim", c5="item/wing.n3cpart",
                                           c6="item/green.n3cpart", c7="item/glow.n3cpart")])
more, failed, more_report = ko_npc_looks.convert(client2, ["demo:looks/800", "demo:looks/300"], out2 / "root", "demo",
                                                 out2 / "work")
assert not failed and [e["key"] for e in more] == ["demo:looks/300", "demo:looks/800"], (failed, more)
idle = (out2 / "root" / more[1]["clips"][0]["source"]).read_bytes()
assert idle[:4] == b"N3SM" and (out2 / "root" / more[0]["clips"][0]["source"]).read_bytes()[:4] == b"N3S1"
width, height = struct.unpack_from("<II", idle, 4)
texels = idle[12:12 + width * height * 4]
assert {texels[i + 3] for i in range(0, len(texels), 4)} >= {0, 255, 8 * 17}
# Runs: 3 indices each (one triangle a part), flags 2 (double-sided), 0, 5
# (blend + unlit) with source alpha / one minus source alpha.
tail = idle[-16 - 4 - 3 * 24:-16]
assert struct.unpack("<I", tail[:4])[0] == 3
assert [struct.unpack_from("<IIIfII", tail, 4 + 24 * i) for i in range(3)] == [
    (0, 3, 2, 0.0, 0, 0), (3, 3, 0, 0.0, 0, 0), (6, 3, 5, 0.0, 4, 5)], tail
assert [p["render_state"]["blend"] for p in json.loads(
    (out2 / "work/800/idle/provenance.json").read_text())["parts"]] == [None, None, ["src_alpha", "one_minus_src_alpha"]]
shutil.copytree(source, out2 / "package-source")
shutil.copytree(out2 / "root/npc-looks-src", out2 / "package-source/npc-looks-src")
m = json.loads((out2 / "package-source/package.json").read_text())
templates = [dict(npc_looks_live.BASE, name="demo:creature/t%d" % i, looks=e["key"]) for i, e in enumerate(more)]
m["gameplay"].update(spawns=npc_looks_live.SPAWNS, spawn_x=npc_looks_live.PLAYER[0], spawn_z=npc_looks_live.PLAYER[1])
m["npc"]["templates"] = templates
m["npc"]["slots"] = [dict(area=[0, 0, 0, 0], respawn_ticks=60, template=t["name"]) for t in templates]
m["editing"]["spawns"] = [0, 1]
m["npc_looks"] = more
assert npc_looks.engine(more, out2 / "package-source") == 39
m.update(engine_version=39, protocol_version=30)
(out2 / "package-source/package.json").write_text(json.dumps(m))
main.cook(out2 / "package-source", out2 / "package")
assert [(out2 / "package" / ("npc-looks-%d.bin" % i)).read_bytes()[:4] for i in range(2)] == [b"N3NM", b"N3MM"]
lines = npc_looks_live.check_readers((out2 / "package").resolve())
measured = next(line for line in lines if line.startswith("npc looks "))
assert measured.startswith("npc looks 2 "), measured
print("PASS a looks row with part render states converts into N3SM clips (runs in part order, alpha kept) and "
      "cooks into an N3MM model in an engine 39 package both readers accept (%s)" % measured)
