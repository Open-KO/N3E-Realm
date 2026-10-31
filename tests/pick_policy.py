"""Package actor pick policy (PQ-146, D-138): cooker validation, client and
server readers, and the cooked demo values (KO 0041c300 and 0041c7d0)."""
import json, os, shutil, struct, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path("tools/assetc").resolve()))
import main, pick
from common import digest, f, string, u


def refused(policy, why):
    try:
        pick.cook(policy)
    except ValueError:
        return
    raise AssertionError("cooker accepted " + why)


ko = {"box": "joints", "min_extent": 0.5, "pad": 0.25, "mesh_lod": 1}
demo_policy = {**ko, "box": "vertices"}
assert pick.cook(ko) == b"N3PK" + u(1) + f([0.5, 0.25]) + u(1)
assert pick.cook(demo_policy) == b"N3PK" + u(0) + f([0.5, 0.25]) + u(1)
assert json.loads(Path("games/moradon/pick.json").read_text()) == ko, "the KO package uses KO's joint box"
refused({**ko, "extra": 1}, "an unknown field")
refused({"box": "joints", "min_extent": 0.5, "pad": 0.25}, "a missing field")
refused({**ko, "box": "mesh"}, "an unknown box source")
refused({**ko, "box": ["joints"]}, "a list box source")
refused({**ko, "min_extent": -0.1}, "a negative minimum")
refused({**ko, "pad": 4.5}, "an oversized padding")
refused({**ko, "pad": float("nan")}, "a NaN padding")
refused({**ko, "pad": True}, "a boolean padding")
refused({**ko, "mesh_lod": 4}, "a LOD beyond 3")
refused({**ko, "mesh_lod": 1.0}, "a non-integer LOD")
refused([0.5, 0.25, 1], "a list")


def readers(out, client=True, server=True):
    for command, good in [(["build/client/n3e-asset-check", str(out)], client),
                          (["target/debug/n3e-server", "--check-content"], server)]:
        p = subprocess.run(command, env={**os.environ, "N3E_PACKAGE": str(out)}, capture_output=True, text=True)
        assert (p.returncode == 0) == good, (command, p.stdout, p.stderr)


def rehash(out, name, data):
    """Rewrite one cooked file and the release index, so readers reach the parser."""
    (out / name).write_bytes(data)
    raw = (out / "release.bin").read_bytes()
    at = 16
    for _ in range(2):
        n = struct.unpack_from("<I", raw, at)[0]
        at += 4 + n
    head, count = raw[:at], struct.unpack_from("<I", raw, at)[0]
    at += 4
    entries = []
    for _ in range(count):
        n = struct.unpack_from("<I", raw, at)[0]
        at += 4
        key = raw[at:at + n].decode()
        at += n + 36
        content = (out / key).read_bytes()
        entries.append(string(key) + u(len(content)) + digest(content))
    (out / "release.bin").write_bytes(head + u(count) + b"".join(entries))


demo = Path("build/packages/demo")
assert (demo / "pick.bin").read_bytes() == pick.cook(demo_policy), "the demo package: vertex box, KO's extent and LOD split"
readers(demo)

with tempfile.TemporaryDirectory(dir="build") as tmp:
    source, out = Path(tmp) / "source", Path(tmp) / "release"
    shutil.copytree("games/demo", source)
    manifest = json.loads((source / "package.json").read_text())
    # A valid KO policy round-trips through both readers.
    manifest["pick"] = ko
    (source / "package.json").write_text(json.dumps(manifest))
    main.cook(source, out)
    readers(out)
    # Out-of-bounds or malformed policies: both readers refuse.
    for data in [u(1) + f([-1, 0.25]) + u(1), u(1) + f([0.5, 5]) + u(1), u(1) + f([0.5, 0.25]) + u(4),
                 u(2) + f([0.5, 0.25]) + u(1), u(1) + f([float("nan"), 0.25]) + u(1), u(1) + f([0.5, 0.25]) + u(1) + b"\0",
                 u(1) + f([0.5, 0.25])]:
        data = b"N3PK" + data
        main.cook(source, out)
        rehash(out, "pick.bin", data)
        readers(out, client=False, server=False)
    main.cook(source, out)
    rehash(out, "pick.bin", b"N3PJ" + u(1) + f([0.5, 0.25]) + u(1))
    readers(out, client=False, server=False)
    # Without a policy the release keeps working (vertex box, no minimum, mesh at every LOD).
    del manifest["pick"]
    (source / "package.json").write_text(json.dumps(manifest))
    main.cook(source, out)
    assert not (out / "pick.bin").exists()
    readers(out)
print("PASS pick policy: cooker refuses bad fields, client and server refuse bad bounds, source or magic, "
      "KO and demo policies cooked, absent policy accepted")
