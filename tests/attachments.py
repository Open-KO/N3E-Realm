"""PQ-328 attached characters (N3AT): the cooker's bounds and refusals on
original synthetic models (tools/assetc/attachment_fixture.py), the table it
writes, and the engine a package with attachments needs. PQ-317: the skeletal
plug entries (tools/assetc/skeletal_plug_fixture.py), their placement and
clip map, and their refusals. No KO data, no
containers; both readers on a whole package are tests/attached_characters_live.py.
"""
import copy
from pathlib import Path
import struct
import sys
import tempfile

sys.path.insert(0, str(Path("tools/assetc").resolve()))
import attachment_fixture as fixture  # noqa: E402
import attachments  # noqa: E402
import skeletal_plug_fixture as bow_fixture  # noqa: E402
import npc_looks  # noqa: E402

APPEARANCE = [dict(item="demo:item/blade", slot=0), dict(item="demo:item/wing", slot=4),
              dict(item="demo:item/fairy", slot=5)]
CLOCK = dict(per_attachment=True, rise=1.0, hold=3.0, fall=5.0, period=5.5)

with tempfile.TemporaryDirectory(dir="build") as tmp:
    root = Path(tmp)
    count, first = fixture.indices("fairy")
    policy = dict(clock=dict(CLOCK), color=[1.0, 1.0, 1.0], entries=[
        dict(item="demo:item/wing", slot=4, joint=1, scale=1.0, group=0, optional=True, emissive=True, modulate=2,
             lit="all", clips=fixture.write(root, "wing", "wing")),
        dict(item="demo:item/fairy", slot=5, joint=1, scale=1.1, group=1, optional=False, emissive=False,
             modulate=2, lit=first, clips=fixture.write(root, "fairy", "fairy")),
    ])
    files, deps = attachments.cook(policy, root, APPEARANCE, {})
    assert sorted(files) == ["attachment-0.bin", "attachment-1.bin", "attachments.bin"] and len(deps) == 8, files
    table = files["attachments.bin"]
    # Header: magic, flags (per attachment), the pulse, the colour, the count.
    assert table[:8] == b"N3AT" + struct.pack("<I", 1), table[:8]
    assert struct.unpack_from("<7fI", table, 8) == (1.0, 3.0, 5.0, 5.5, 1.0, 1.0, 1.0, 2), table[8:40]
    # Entries: key, joint, scale, group, flags, modulate, lit, then four clips.
    wing = struct.unpack_from("<IIfIIfI", table, 40)
    assert wing == (2, 1, 1.0, 0, 3, 2.0, len(fixture.wing()[1])), wing
    fairy = struct.unpack_from("<IIfIIfI", table, 40 + 7 * 4 + 4 * 20)
    assert fairy[:2] == (3, 1) and abs(fairy[2] - 1.1) < 1e-6 and fairy[3:] == (1, 0, 2.0, first), fairy
    assert first < count
    assert len(table) == 40 + 2 * (7 * 4 + 4 * 20)
    # The model stores the atlas and mesh once and the four track lists, as a looks model.
    clips = [(root / c["source"]).read_bytes() for c in policy["entries"][0]["clips"]]
    head, _, tail, _ = npc_looks.split_scene(clips[0])
    assert files["attachment-0.bin"] == b"N3NM" + head + b"".join(npc_looks.split_scene(c)[1] for c in clips) + tail
    assert attachments.engine(policy, root) == 38

    def rejects(change, appearance=APPEARANCE):
        bad = copy.deepcopy(policy)
        change(bad)
        try:
            attachments.cook(bad, root, appearance, {})
        except (ValueError, KeyError, TypeError):
            return
        raise AssertionError("cooker accepted a bad attachment policy")

    e = lambda p, i=0: p["entries"][i]  # noqa: E731
    rejects(lambda p: p["entries"].clear())
    rejects(lambda p: p["entries"].extend([e(p)] * 15))  # 17 entries
    rejects(lambda p: p.update(extra=1))
    rejects(lambda p: e(p).update(extra=1))
    rejects(lambda p: e(p, 1).update(item="demo:item/wing", slot=4))  # the same key twice
    rejects(lambda p: e(p).update(slot=5))  # no appearance row (wing, 5)
    rejects(lambda p: e(p).update(item="demo:item/cape"))  # no appearance row
    rejects(lambda p: e(p).update(joint=64))
    rejects(lambda p: e(p).update(joint=-1))
    rejects(lambda p: e(p).update(scale=0))
    rejects(lambda p: e(p).update(scale=float("nan")))
    rejects(lambda p: e(p).update(group=16))
    rejects(lambda p: e(p).update(optional=1))
    rejects(lambda p: e(p).update(emissive="yes"))
    rejects(lambda p: e(p).update(modulate=3))
    rejects(lambda p: e(p).update(modulate=True))
    rejects(lambda p: e(p, 1).update(lit=13))  # not whole triangles
    rejects(lambda p: e(p, 1).update(lit=count + 3))  # past the mesh
    rejects(lambda p: e(p, 1).update(lit="first"))
    rejects(lambda p: p["clock"].update(rise=0))
    rejects(lambda p: p["clock"].update(hold=.5))  # before the rise ends
    rejects(lambda p: p["clock"].update(period=61))
    rejects(lambda p: p["clock"].update(per_attachment=1))
    rejects(lambda p: p.update(color=[1.5, 1, 1]))
    rejects(lambda p: p.update(color=[1, 1]))
    rejects(lambda p: e(p)["clips"].pop())  # three clips
    rejects(lambda p: e(p)["clips"][2].update(loop_blend=True))  # a looping attack
    rejects(lambda p: e(p)["clips"][0].update(duration=.5))  # differs from the clip's keys
    rejects(lambda p: e(p)["clips"][1].update(source=e(p, 1)["clips"][1]["source"]))  # another mesh
    print("PASS attachment cook: N3AT header and entries, models as looks models, engine 38, "
          "and every malformed policy refused")

    # PQ-317: a skeletal plug entry beside the wing, on its own appearance key.
    plugged = APPEARANCE + [dict(item="demo:item/bow", slot=1)]
    rows = bow_fixture.CLIP_MAP + [dict(kind="combat", id=1, slot=1, once=True),
                                   dict(kind="skill", id=17, slot=2, once=True)]
    plug_policy = copy.deepcopy(policy)
    plug_policy["entries"].append(dict(item="demo:item/bow", slot=1, joint=1, scale=1.0, group=2,
                                       plug=dict(placement=list(bow_fixture.PLACEMENT), clips=rows),
                                       clips=bow_fixture.write(root)))
    files, deps = attachments.cook(plug_policy, root, plugged, {}, combat_clips=2, skill_animations={16, 17})
    table = files["attachments.bin"]
    at = 40 + 2 * (7 * 4 + 4 * 20)
    # The base fields: key 4, joint 1, scale 1, group 2, flags 4 (plug), modulate 1, lit 0.
    assert struct.unpack_from("<IIfIIfI", table, at) == (4, 1, 1.0, 2, 4, 1.0, 0), table[at:at + 28]
    at += 7 * 4 + 4 * 20
    assert struct.unpack_from("<12f", table, at) == tuple(struct.unpack("<12f", struct.pack("<12f", *bow_fixture.PLACEMENT)))
    at += 48
    assert struct.unpack_from("<I", table, at)[0] == len(rows)
    written = [struct.unpack_from("<4I", table, at + 4 + 16 * i) for i in range(len(rows))]
    kinds = dict(state=0, combat=1, skill=2)
    assert written == [(kinds[r["kind"]], r["id"], r["slot"], int(r["once"])) for r in rows], written
    assert len(table) == at + 4 + 16 * len(rows)
    assert attachments.engine(plug_policy, root) == 38 and len(files) == 4 and len(deps) == 12

    def refuses(change, **context):
        bad = copy.deepcopy(plug_policy)
        change(bad["entries"][2])
        try:
            attachments.cook(bad, root, plugged, {}, **{"combat_clips": 2, "skill_animations": {16, 17}, **context})
        except (ValueError, KeyError, TypeError):
            return 1
        raise AssertionError("cooker accepted a bad plug entry")
    plug_refused = sum([
        refuses(lambda b: b.update(optional=False)),  # a plug names no optional, emissive, modulate or lit
        refuses(lambda b: b.update(lit=0)),
        refuses(lambda b: b["plug"].update(extra=1)),
        refuses(lambda b: b["plug"]["placement"].pop()),
        refuses(lambda b: b["plug"].update(placement=[0.0] * 12)),  # singular
        refuses(lambda b: b["plug"]["placement"].__setitem__(3, 101.0)),
        refuses(lambda b: b["plug"]["placement"].__setitem__(0, float("nan"))),
        refuses(lambda b: b["plug"].update(clips=[])),
        refuses(lambda b: b["plug"].update(clips=[dict(kind="state", id=0, slot=0, once=False)] * 2)),  # twice
        refuses(lambda b: b["plug"].update(clips=[dict(kind="state", id=i % 10, slot=0, once=False) for i in range(65)])),
        refuses(lambda b: b["plug"]["clips"][0].update(kind="pose")),
        refuses(lambda b: b["plug"]["clips"][0].update(id=10)),  # past the pose states
        refuses(lambda b: b["plug"]["clips"][0].update(slot=4)),
        refuses(lambda b: b["plug"]["clips"][0].update(once=1)),
        refuses(lambda b: b["plug"]["clips"][0].update(extra=1)),
        refuses(lambda b: b["plug"]["clips"][-2].update(id=2)),  # past the package's two combat clips
        refuses(lambda b: b["plug"]["clips"][-1].update(id=18)),  # no such skill animation
        refuses(lambda b: None, combat_clips=1),
        refuses(lambda b: None, skill_animations={16}),
    ])
    print(f"PASS skeletal plug cook: flag 4, modulate 1, lit 0, the placement rows and the clip map after the "
          f"clips, and {plug_refused} malformed plug entries refused")
