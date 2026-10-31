"""PQ-316 (D-185): the package screen post-process (postprocess.bin, N3PF).

The cooker (tools/assetc/postprocess.py) refuses missing, extra, non-numeric,
non-finite and out-of-bound fields, and a package below engine 33 or without
the presentation assets; its bytes are N3PF and seven f32 in field order, and
the client's reader (build/client/n3e-postprocess-check FILE) reads them back
and refuses malformed files the same way. The server's reader has its own
unit tests (cargo test postprocess); tests/postprocess_live.py runs both
readers on a cooked release and the graphical chain.
"""
import json
import math
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/assetc"))
import main  # noqa: E402
import postprocess  # noqa: E402

CHECK = ROOT / "build/client/n3e-postprocess-check"
MORADON = dict(threshold=0.367, bloom=0.7, exposure=0.1, saturation=1.0, lift=0.65, adapt_rate=0.3, blur_variance=1.0)


def refused(c, why):
    try:
        postprocess.cook(c)
    except ValueError:
        return
    raise AssertionError("cooker accepted " + why)


cooked = postprocess.cook(MORADON)
assert cooked == b"N3PF" + struct.pack("<7f", *MORADON.values()), cooked
assert len(cooked) == postprocess.SIZE == 32
assert postprocess.parse(cooked) == {k: struct.unpack("<f", struct.pack("<f", v))[0] for k, v in MORADON.items()}
assert postprocess.cook({**MORADON, "blur_variance": 1e-30})  # small but not 0 in f32
refused({**MORADON, "extra": 1}, "an unknown field")
refused({k: v for k, v in MORADON.items() if k != "lift"}, "a missing field")
refused([0.367, 0.7], "a list")
for name, (low, high, open_low) in postprocess.BOUNDS.items():
    refused({**MORADON, name: high + 0.01}, name + " above its bound")
    refused({**MORADON, name: low - 0.01}, name + " below its bound")
    refused({**MORADON, name: float("nan")}, name + " NaN")
    refused({**MORADON, name: math.inf}, name + " infinite")
    refused({**MORADON, name: True}, name + " boolean")
    refused({**MORADON, name: "1"}, name + " string")
    if open_low:
        refused({**MORADON, name: low}, name + " at its open bound")
        refused({**MORADON, name: 1e-46}, name + " above its open bound but 0 in f32")
    else:
        postprocess.cook({**MORADON, name: low})
    postprocess.cook({**MORADON, name: high})

with tempfile.TemporaryDirectory(dir=ROOT / "build") as tmp:
    tmp = Path(tmp)
    good = tmp / "postprocess.bin"
    good.write_bytes(cooked)
    p = subprocess.run([str(CHECK), str(good)], capture_output=True, text=True)
    assert p.returncode == 0 and "threshold=0.367 bloom=0.7 exposure=0.1 saturation=1 lift=0.65" in p.stdout, p
    body = list(MORADON.values())
    bad = {
        "magic": b"N3PG" + cooked[4:],
        "truncated": cooked[:-4],
        "trailing": cooked + b"\0",
        "variance zero": b"N3PF" + struct.pack("<7f", *body[:6], 0.0),
        "threshold high": b"N3PF" + struct.pack("<7f", 1.5, *body[1:]),
        "lift negative": b"N3PF" + struct.pack("<7f", *body[:4], -0.5, *body[5:]),
        "NaN": b"N3PF" + struct.pack("<7f", *body[:2], float("nan"), *body[3:]),
    }
    for name, data in bad.items():
        path = tmp / f"bad-{name.replace(' ', '-')}.bin"
        path.write_bytes(data)
        p = subprocess.run([str(CHECK), str(path)], capture_output=True, text=True)
        assert p.returncode != 0, (name, p.stdout)
        try:
            postprocess.parse(data)
        except ValueError:
            pass
        else:
            raise AssertionError("parse accepted " + name)
    # The cook refuses the key below engine 33 (the demo package is engine 11).
    source = tmp / "demo"
    shutil.copytree(ROOT / "games/demo", source)
    manifest = json.loads((source / "package.json").read_text())
    assert manifest["engine_version"] < 33
    manifest["postprocess"] = MORADON
    (source / "package.json").write_text(json.dumps(manifest))
    try:
        main.cook(source, tmp / "out")
    except ValueError as e:
        assert str(e) == "postprocess compatibility", e
    else:
        raise AssertionError("cooked a postprocess below engine 33")
print(f"PASS postprocess: N3PF cooked in field order ({len(cooked)} bytes); the cooker refuses missing, extra, "
      f"non-numeric, non-finite and out-of-bound fields and engine < 33; the client reader reads it back and refuses "
      f"{len(bad)} malformed files")
