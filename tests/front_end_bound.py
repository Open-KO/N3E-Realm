"""RQ-183: front-end.bin's 256 MiB bound (content/front-end.md, spec 11) through
the package cook (tools/assetc/main.py FRONT_END_FILE), the client's release
load (build/client/n3e-asset-check: kFrontEndFile, hashed in blocks) and the
server's (n3e-server --check-content: MAX_FRONT_END_ASSET, hashed in blocks, the
slot count read from the header alone). The loader of the whole file
(n3e-front-end-check, and ko_front_end's own bound) is tests/front_end.py's.

Synthetic, no KO data: the engine 41 package of tests/npc_scale_live.py made
engine 42 with a front-end.bin of a version 31 header (3 slots, 1024x768) and
zeros, which neither the cook nor either release load reads past. A file past
64 MiB passes all three; one exactly 256 MiB passes both release loads; one a
byte past 256 MiB is refused by each for its size. The files are under build/,
sparse where nothing reads them whole, and removed after."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "tools/assetc"))
sys.path.append(str(ROOT / "tests"))
import main  # noqa: E402
import ko_front_end  # noqa: E402
from common import string, u  # noqa: E402
import npc_scale_live  # noqa: E402

BOUND = 256 << 20
assert main.FRONT_END_FILE == ko_front_end.MAX_FILE == BOUND, (main.FRONT_END_FILE, ko_front_end.MAX_FILE)
HEADER = b"N3FE" + struct.pack("<4I", ko_front_end.VERSION, 3, 1024, 768)
BIG = (64 << 20) + (1 << 20)


def front_end(path, size, sparse=True):
    """A front-end.bin of `size` bytes: the header, then zeros (a hole if `sparse`)."""
    with open(path, "wb") as f:
        f.write(HEADER)
        if sparse:
            f.truncate(size)
        else:
            f.write(bytes(size - len(HEADER)))


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(1 << 20):
            h.update(block)
    return h.digest()


def readers(out, good, why=("", "")):
    """The client's asset check and the server's content check on `out`."""
    for cmd, reason in zip((["build/client/n3e-asset-check", str(out)], ["target/debug/n3e-server", "--check-content"]),
                           why):
        p = subprocess.run(cmd, env={**os.environ, "N3E_PACKAGE": str(out)}, capture_output=True, text=True)
        assert (p.returncode == 0) == good, (cmd, p.stdout[-400:], p.stderr[-400:])
        assert reason in p.stderr, (cmd, reason, p.stderr[-400:])


def reindex(out, size):
    """`out` with front-end.bin a sparse file of `size` bytes, its release index
    carrying the file's true length and digest."""
    m = json.loads((out / "recipe.json").read_text())["manifest"]
    front_end(out / "front-end.bin", size)
    names = sorted(p.name for p in out.iterdir() if p.name not in ("release.bin", "release.sha256"))
    index = b"N3R1" + u(1) + u(m["engine_version"]) + u(m["protocol_version"]) + string(m["game_id"]) + \
        string(m["package_version"]) + u(len(names))
    for name in names:
        index += string(name) + u((out / name).stat().st_size) + digest(out / name)
    (out / "release.bin").write_bytes(index)
    (out / "release.sha256").write_text(hashlib.sha256(index).hexdigest() + "\n")


(ROOT / "build").mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=ROOT / "build", prefix="front-end-bound-") as td:
    source = npc_scale_live.prepare().parent / "source"
    root, out = Path(td) / "source", Path(td) / "package"
    shutil.copytree(source, root)
    m = json.loads((root / "package.json").read_text())
    m["presentation"]["front-end.bin"] = "front-end.bin"
    m["engine_version"] = 42
    (root / "package.json").write_text(json.dumps(m))

    # Past the old 64 MiB: the cook takes it, both release loads take the package.
    front_end(root / "front-end.bin", BIG, sparse=False)
    main.cook(root, out)
    assert (out / "front-end.bin").stat().st_size == BIG
    readers(out, True)
    print("PASS front-end.bin of %d bytes (past 64 MiB): cooked, and loaded by the client's and the server's "
          "release loads" % BIG)

    # A byte past 256 MiB: the cook refuses it for its size.
    front_end(root / "front-end.bin", BOUND + 1)
    try:
        main.cook(root, Path(td) / "refused")
        raise AssertionError("the cook took a front-end.bin a byte past 256 MiB")
    except ValueError as error:
        assert str(error) == "file exceeds 256 MiB", error
    (root / "front-end.bin").unlink()

    # The release loads on the package re-indexed: exactly 256 MiB loads, a
    # byte past is refused for its size (not its hash, which the index carries).
    reindex(out, BOUND)
    readers(out, True)
    reindex(out, BOUND + 1)
    readers(out, False, ("asset file bound", "file bound"))
print("PASS front-end.bin's 256 MiB bound: exactly 256 MiB loaded by both release loads; a byte past refused by "
      "the cook and both release loads for its size")
