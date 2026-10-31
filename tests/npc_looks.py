"""PQ-253 per-template NPC presentation (N3LK + N3NM, engine 38 / wire 30):
cooker bounds, both readers on the synthetic packages of
tests/npc_looks_live.py, forged tables and models failing closed in both, and
the 52-looks load measured by the client's reader. No KO data, no containers.
"""
import copy
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path("tools/assetc").resolve()))
sys.path.append(str(Path("tests").resolve()))
import npc_looks  # noqa: E402
import npc_looks_fixture as fixture  # noqa: E402
from common import digest, string, u  # noqa: E402
import npc_looks_live  # noqa: E402

# Cooker: a two-entry policy on scratch clips.
with tempfile.TemporaryDirectory(dir="build") as tmp:
    root = Path(tmp)
    policy = [dict(key="demo:looks/a", name_always=False, clips=fixture.write(root, "a", "pillar", (200, 0, 0))),
              dict(key="demo:looks/b", name_always=True, clips=fixture.write(root, "b", "slab", (0, 0, 200)))]
    templates = [dict(looks="demo:looks/a"), dict(looks="demo:looks/b"), dict(looks="demo:looks/a")]
    files, deps = npc_looks.cook(policy, root, "demo", templates)
    assert sorted(files) == ["npc-looks-0.bin", "npc-looks-1.bin", "npc-looks.bin"] and len(deps) == 8, files.keys()
    table = files["npc-looks.bin"]
    assert table[:8] == b"N3LK" + u(2) and table[8:8 + 16] == string("demo:looks/a"), table[:24]
    # The model stores the atlas and mesh once and the four track lists.
    clips = [(root / c["source"]).read_bytes() for c in policy[0]["clips"]]
    head, _, tail, atlas = npc_looks.split_scene(clips[0])
    assert files["npc-looks-0.bin"] == b"N3NM" + head + b"".join(npc_looks.split_scene(c)[1] for c in clips) + tail
    assert len(files["npc-looks-0.bin"]) < sum(len(c) for c in clips)

    def rejects(change, game="demo", looks=templates):
        bad = copy.deepcopy(policy)
        change(bad)
        try:
            npc_looks.cook(bad, root, game, looks)
        except (ValueError, KeyError, TypeError):
            return
        raise AssertionError("cooker accepted a bad looks policy")

    rejects(lambda p: p.clear())
    rejects(lambda p: p.extend([p[0]] * 127))  # 129 entries
    rejects(lambda p: p[1].update(key="demo:looks/a"))  # duplicate key
    rejects(lambda p: p[1].update(key="other:looks/b"))  # outside the namespace
    rejects(lambda p: p[1].update(key="demo:Looks/B"))  # outside the rule-ID alphabet
    rejects(lambda p: p[0].update(name_always=1))
    rejects(lambda p: p[0].update(extra=1))
    rejects(lambda p: p[0]["clips"].pop())  # three clips
    rejects(lambda p: p[0]["clips"][2].update(loop_blend=True))  # a looping attack
    rejects(lambda p: p[0]["clips"][3].update(loop_blend=True))  # a looping death
    rejects(lambda p: p[0]["clips"][0].update(duration=0.5))  # differs from the clip's keys
    rejects(lambda p: p[0]["clips"][2].update(markers=[0.7, -1]))  # marker past the duration
    rejects(lambda p: p[0]["clips"][1].update(source=p[1]["clips"][1]["source"]))  # another mesh
    rejects(lambda p: None, looks=templates[:1])  # an entry no template uses
    rejects(lambda p: None, looks=templates + [dict(looks="demo:looks/c")])  # a template without an entry
    (root / "bad.bin").write_bytes(b"N3S2" + clips[0][4:])
    rejects(lambda p: p[0]["clips"][0].update(source="bad.bin"))
    # The atlas budget (96 MiB over every looks) and the per-model file bound.
    saved = npc_looks.MAX_TEXTURE_BYTES
    npc_looks.MAX_TEXTURE_BYTES = 2 * atlas - 1
    rejects(lambda p: None)
    npc_looks.MAX_TEXTURE_BYTES = saved
    big = fixture.write(root, "big", "pillar", (1, 2, 3), 1024)
    big_files, _ = npc_looks.cook([dict(key="demo:looks/a", name_always=False, clips=big)], root, "demo",
                                  [dict(looks="demo:looks/a")])
    assert len(big_files["npc-looks-0.bin"]) < 16 * 1024 * 1024
print("PASS N3LK/N3NM cooker: shared atlas and mesh stored once, keys, flags, clip bounds, coverage and budgets")

# Both readers on the synthetic engine 38 packages (no KO data).
package = npc_looks_live.prepare()
bound = npc_looks_live.prepare(npc_looks_live.BOUND_LOOKS)
lines = npc_looks_live.check_readers(bound)
measured = next(line for line in lines if line.startswith("npc looks "))
assert measured.startswith(f"npc looks {npc_looks_live.BOUND_LOOKS} texture_bytes "), measured
print(f"PASS both readers accept the {npc_looks_live.BOUND_LOOKS}-looks package; client reader: {measured}")


def readers(out, good, why="", label=""):
    for cmd in [["build/client/n3e-asset-check", str(out)], ["target/debug/n3e-server", "--check-content"]]:
        p = subprocess.run(cmd, env={**os.environ, "N3E_PACKAGE": str(out)}, capture_output=True, text=True)
        assert (p.returncode == 0) == good, (cmd, label or why, p.stdout[-400:], p.stderr[-400:])
        if not good and why:
            assert why in p.stderr, (cmd, why, p.stderr[-400:])


def forge(source, change, engine=38, protocol=30):
    """Copy of `source` with its files changed by `change(files)`, re-indexed."""
    tmp = tempfile.TemporaryDirectory(dir="build")
    out = Path(tmp.name) / "release"
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
    return tmp, out


def check(source, change, good, why="", label="", **kw):
    tmp, out = forge(source, change, **kw)
    with tmp:
        readers(out, good, why, label)


check(package, lambda f: None, True)
table = (package / "npc-looks.bin").read_bytes()
key_length = struct.unpack_from("<I", table, 8)[0]
flags_at = 12 + key_length
clips_at = flags_at + 4  # four records of duration, blend, loop, two markers


def entry(at):
    """The bytes of the table entry starting at `at`: key, flags, four clips."""
    return table[at:at + 4 + struct.unpack_from("<I", table, at)[0] + 4 + 4 * 20]


first = entry(8)


def patch(offset, value, fmt="<I"):
    data = bytearray(table)
    struct.pack_into(fmt, data, offset, value)
    return bytes(data)


for name, data in [
        ("count 0", table[:4] + u(0) + table[8:]), ("count 129", table[:4] + u(129) + table[8:]),
        ("magic", b"N3LJ" + table[4:]), ("trailing", table + b"\0"), ("truncated", table[:-1]),
        ("flags 2", patch(flags_at, 2)), ("duration 0", patch(clips_at, 0.0, "<f")),
        ("blend 3", patch(clips_at + 4, 3.0, "<f")), ("attack loops", patch(clips_at + 2 * 20 + 8, 1)),
        ("marker past duration", patch(clips_at + 2 * 20 + 12, 5.0, "<f")),
        ("key outside the namespace", table.replace(b"demo:looks/pillar", b"oops:looks/pillar", 1)),
        ("unknown key", table.replace(b"demo:looks/pillar", b"demo:looks/pillaz", 1)),
        ("duplicate key", table[:8] + first + first),
        ("one entry for two templates", table[:4] + u(1) + first)]:
    check(package, lambda f, d=data: f.update({"npc-looks.bin": d}), False, label=name)
# A missing model, an extra file, a model with another magic or an oversized atlas.
check(package, lambda f: f.pop("npc-looks-1.bin"), False, "npc looks model")
check(package, lambda f: f.update({"npc-looks-2.bin": f["npc-looks-1.bin"]}), False)
check(package, lambda f: f.update({"npc-looks-1.bin": b"N3S1" + f["npc-looks-1.bin"][4:]}), False)
check(package, lambda f: f.update({"npc-looks-1.bin": b"N3NM" + u(1025) + f["npc-looks-1.bin"][8:]}), False)
# Without its table, an engine 38 package fails; an engine 37 package may not carry one.
check(package, lambda f: [f.pop(n) for n in list(f) if n.startswith("npc-looks")], False, "npc looks compatibility")
check(package, lambda f: None, False, "npc looks compatibility", engine=37, protocol=30)
check(package, lambda f: None, False, "incompatible", engine=38, protocol=31)
# The budgets: every model's header claims a 1024 x 1024 atlas (52 x 3 MiB =
# 156 MiB of atlases > 96 MiB); both readers refuse before parsing or
# uploading any model (the release index has already read and hashed each file).
check(bound, lambda f: f.update({n: d[:4] + u(1024) + u(1024) + d[12:] for n, d in f.items()
                                  if n.startswith("npc-looks-")}), False, "npc looks byte budget")
print("PASS both readers accept the engine 38 package and refuse forged looks tables, missing, extra and "
      "foreign models, an atlas over 1024, a looks file in engine 37, engine 38 without one or with wire 31, and "
      "atlases over the 96 MiB budget")

# PQ-265 (D-173): looks models with render states. Four N3SM clips cook into
# one N3MM model (RGBA atlas, runs in the tail); clips of both kinds in one
# entry are refused; the atlas budget counts four bytes a texel; a package
# with an N3MM model is engine 39 (the cooker refuses it declared 38).
import npc_materials_live  # noqa: E402

with tempfile.TemporaryDirectory(dir="build") as tmp:
    root = Path(tmp)
    parts, rgba = npc_materials_live.models(fixture)["demo:looks/glass"]
    glass = fixture.write_materials(root, "glass", parts, *npc_materials_live.ATLAS, rgba)
    plain = fixture.write(root, "plain", "pillar", (200, 0, 0))
    policy = [dict(key="demo:looks/a", name_always=False, clips=glass),
              dict(key="demo:looks/b", name_always=False, clips=plain)]
    two = [dict(looks="demo:looks/a"), dict(looks="demo:looks/b")]
    files, _ = npc_looks.cook(policy, root, "demo", two)
    clips = [(root / c["source"]).read_bytes() for c in glass]
    head, _, tail, atlas = npc_looks.split_scene(clips[0])
    assert atlas == 24 * 8 * 4 and files["npc-looks-1.bin"][:4] == b"N3NM"
    assert files["npc-looks-0.bin"] == b"N3MM" + head + b"".join(npc_looks.split_scene(c)[1] for c in clips) + tail
    assert npc_looks.engine(policy, root) == 39 and npc_looks.engine(policy[1:], root) == 38
    mixed = copy.deepcopy(policy)
    mixed[0]["clips"][3] = dict(mixed[0]["clips"][3], source=plain[3]["source"])
    try:
        npc_looks.cook(mixed, root, "demo", two)
    except ValueError:
        pass
    else:
        raise AssertionError("cooker accepted N3S1 and N3SM clips in one looks")
    saved = npc_looks.MAX_TEXTURE_BYTES
    npc_looks.MAX_TEXTURE_BYTES = 24 * 8 * 4 + 4 * 4 * 3 - 1
    try:
        npc_looks.cook(policy, root, "demo", two)
    except ValueError:
        pass
    else:
        raise AssertionError("cooker counted an RGBA atlas at three bytes a texel")
    npc_looks.MAX_TEXTURE_BYTES = saved
materials = npc_materials_live.prepare()
source = npc_materials_live.OUT / "source"
m = json.loads((source / "package.json").read_text())
assert m["engine_version"] == 39
m["engine_version"] = 38
with tempfile.TemporaryDirectory(dir="build") as tmp:
    shutil.copytree(source, Path(tmp) / "source")
    (Path(tmp) / "source/package.json").write_text(json.dumps(m))
    try:
        sys.path.insert(0, str(Path("tools/assetc").resolve()))
        import main  # noqa: E402
        main.cook(Path(tmp) / "source", Path(tmp) / "out")
    except ValueError:
        pass
    else:
        raise AssertionError("cooker accepted N3MM looks in an engine 38 package")
print("PASS N3MM cooker: N3SM clips share atlas, mesh and runs in one model, no mixed clip kinds, RGBA counted at "
      "four bytes a texel, engine 39 only")

lines = npc_looks_live.check_readers(materials)
assert any(line.startswith("npc looks 2 texture_bytes 1536 ") for line in lines), lines
check(materials, lambda f: None, True, engine=39)
# An N3MM model is engine 39 only; an engine 39 package may still carry N3NM.
check(materials, lambda f: None, False, "npc looks model", engine=38)
check(package, lambda f: None, True, engine=39)
check(package, lambda f: None, False, "incompatible", engine=43)  # past the newest engine (42, spec 11)
model = (materials / "npc-looks-0.bin").read_bytes()
runs_at = len(model) - 16 - 4 - 3 * 24  # three runs, then scale (12) and attachment (4)
assert struct.unpack_from("<I", model, runs_at)[0] == 3


def run_patch(offset, value, fmt="<I"):
    data = bytearray(model)
    struct.pack_into(fmt, data, runs_at + offset, value)
    return bytes(data)


# Runs (first +0, count +4, flags +8 (1 blend, 2 double-sided, 4 unlit; 8
# and up refused), alpha reference +12, source +16,
# destination +20) at runs_at + 4 + 24 i; the client reader refuses each forgery (the server
# checks the header and budget only, as for N3NM's mesh).
for name, data, why in [
        ("run count 0", run_patch(0, 0), ""), ("run count 4", run_patch(0, 4), ""),
        ("run count 17", run_patch(0, 17), ""),
        ("gap", run_patch(4 + 24, 39), "render run range"), ("short", run_patch(4 + 24 + 4, 33), "render run"),
        ("not triangles", run_patch(4 + 4, 35), "render run range"),
        ("flags 8", run_patch(4 + 8, 8), "render run state"),
        ("factor 10", run_patch(4 + 24 + 16, 10), "render run state"),
        ("factors without blend", run_patch(4 + 16, 4), "render run state"),
        ("alpha reference 1", run_patch(4 + 12, 1.0, "<f"), "render run state"),
        ("alpha reference NaN", run_patch(4 + 12, float("nan"), "<f"), "finite"),
        ("truncated", model[:-1], "")]:
    tmp, out = forge(materials, lambda f, d=data: f.update({"npc-looks-0.bin": d}), engine=39)
    with tmp:
        p = subprocess.run(["build/client/n3e-asset-check", str(out)], capture_output=True, text=True)
        assert p.returncode != 0 and why in p.stderr, (name, p.stdout[-300:], p.stderr[-300:])
print("PASS both readers accept the engine 39 N3MM package and refuse it as engine 38; the client reader refuses "
      "forged render runs (count, gaps, partial triangles, flags, factors, alpha reference, truncation)")
