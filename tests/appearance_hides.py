"""RQ-207: an appearance key that hides other worn keys (render detail N3DH).

KO's world releases the lower part while the upper item is a robe (1298
00467d50, 0045cd90; 1097 00459c60; specs/KO-FINDINGS.md 8.7), so a worn lower
draws nothing under a robe. N3DH is N3D2 / N3D3 / N3DI / N3DJ with u32 layout
flags after the projection (1 states, 2 tables, 4 hidden keys, always set) and,
after each appearance entry's replacements, the keys that entry hides. On
original synthetic bytes, with no KO data:

- render_detail.serialize writes N3DH only when an entry hides a key (flags 4,
  or 5 with render states): N3D2's bytes plus the flags and each entry's list;
- the client's reader (build/client/n3e-asset-check --hidden-detail) takes it
  and refuses layout flags without 4 or 8 or past 15 (RQ-221's 8, the looks
  parts, is tests/detail_looks.py's), tables before engine 44, a
  hidden key of 0, past the keys, itself or twice, more than 16, a key that
  hides and is hidden, an N3DH that hides nothing, a hidden key with an
  appearance effect or an attached character, and truncated or trailing bytes;
- a cooked engine 29 package with two keys, key 1 hiding key 2, is taken by
  both readers (n3e-asset-check, n3e-server --check-content) with the same
  projection, and the client reports the hidden key; the cook refuses N3DH
  layout flags without 4 or 8, and the server an unknown magic.

The composition (draws neither the hidden key's mesh nor its replacements, in
either order) is build/client/n3e-hud-check's (tests/hud.cpp).
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
from common import digest, string, u  # noqa: E402

CHECK = ROOT / "build/client/n3e-asset-check"


def geometry(slot):
    return ([([x, 0, z], [0, 1, 0], [x, z], [0] * 4, [1, 0, 0, 0], slot) for x, z in [(0, 0), (1, 0), (0, 1)]],
            [0, 1, 2])


# Key 1 (the robe) replaces body slots 1 and 2 and hides key 2 (the lower),
# which replaces slot 2.
ARGS = dict(view=[1.134464, .5, 256], thresholds=[[6, 18, 32, 128]] * 4, workload=[30, 60, 100], world_count=1,
            textures=[[(16, 16, bytes([255]) * 1024)]] * 4, radius=1, levels=[geometry(1)] * 4,
            appearances=[([1, 2], [geometry(3)] * 4), ([2], [geometry(3)] * 4)])
STATE = (3, 0.0, 4, 5)


def forge(hides, **more):
    """N3DH bytes with `hides` as written, past the serializer's own checks."""
    real = render_detail.check_hides
    render_detail.check_hides = lambda hides, count: hides
    try:
        return render_detail.serialize(**dict(ARGS, **more), hides=hides)
    finally:
        render_detail.check_hides = real


def flags(data, value):
    return data[:16] + u(value) + data[20:]


def serializer():
    plain = render_detail.serialize(**ARGS)
    hidden = render_detail.serialize(**ARGS, hides=[[2], []])
    assert plain[:4] == b"N3D2" and hidden[:4] == b"N3DH", (plain[:4], hidden[:4])
    assert hidden[4:16] == plain[4:16] and hidden[16:20] == u(4), hidden[:20]
    assert len(hidden) == len(plain) + 4 + 4 * 2 + 4, (len(hidden), len(plain))
    assert render_detail.serialize(**ARGS, hides=[[], []]) == plain, "nothing hidden keeps the N3D2 bytes"
    stated = render_detail.serialize(**ARGS, hides=[[2], []], states=[STATE, STATE])
    assert stated[:4] == b"N3DH" and render_detail.layout(stated[:20]) == 5, stated[:20]
    assert len(stated) == len(render_detail.serialize(**ARGS, states=[STATE, STATE])) + 4 + 4 * 2 + 4
    assert not render_detail.has_tables(stated[:20]) and render_detail.has_tables(flags(stated[:20], 6))
    assert render_detail.has_tables(b"N3DI") and not render_detail.has_tables(b"N3D2")
    assert not render_detail.has_tables(None) and render_detail.layout(hidden[:19]) is None
    print("PASS N3DH serializer: N3D2 / N3D3 bytes plus the layout flags after the projection and each entry's "
          "hidden keys, only when a key is hidden", flush=True)
    return hidden


def reader(data, engine=29, keys=2, effect=0, attachment=0):
    with tempfile.TemporaryDirectory(dir=ROOT / "build") as tmp:
        (Path(tmp) / "render-detail.bin").write_bytes(data)
        return subprocess.run([str(CHECK), "--hidden-detail", tmp, str(engine), str(keys), str(effect),
                               str(attachment)], capture_output=True, text=True)


def client_reader(hidden):
    good = reader(hidden)
    assert good.returncode == 0 and good.stdout.splitlines() == ["key=1 hides=2", "key=2 hides="], \
        (good.stdout, good.stderr)
    stated = render_detail.serialize(**ARGS, hides=[[2], []], states=[STATE, STATE])
    assert reader(stated).stdout.splitlines() == ["key=1 hides=2", "key=2 hides="]
    cases = [
        ("flags 0", flags(hidden, 0), "render detail layout flags"),
        ("flags 3 (no hidden keys)", flags(hidden, 3), "render detail layout flags"),
        ("flags 16", flags(hidden, 16), "render detail layout flags"),
        ("flags 20", flags(hidden, 20), "render detail layout flags"),
        ("states the file lacks", flags(hidden, 5), ""),
        ("tables before engine 44", flags(hidden, 6), "render detail layout flags"),
        ("key 0", forge([[0], []]), "appearance hidden key"),
        ("a key past the keys", forge([[3], []]), "appearance hidden key"),
        ("itself", forge([[1], []]), "appearance hidden key"),
        ("twice", forge([[2, 2], []]), "appearance hidden key"),
        ("17 keys", forge([[2] * 17, []]), ""),
        ("a hiding key hidden", forge([[2], [1]]), "appearance hidden key"),
        ("nothing hidden", nothing_hidden(hidden), "render detail layout flags"),
        ("truncated", hidden[:-1], ""),
        ("trailing", hidden + b"\0", ""),
    ]
    refused = 0
    for name, data, why in cases:
        p = reader(data)
        assert p.returncode != 0 and why in p.stdout + p.stderr, (name, p.stdout[-300:], p.stderr[-300:])
        refused += 1
    # Tables at engine 44 are read as tables: these bytes have none, so the
    # reader fails on the geometry rather than the flags.
    p = reader(flags(hidden, 6), engine=44)
    assert p.returncode != 0 and "layout flags" not in p.stdout + p.stderr, (p.stdout, p.stderr)
    for name, more in [("an effect on the hidden key", dict(effect=2)), ("an attachment on it", dict(attachment=2))]:
        p = reader(hidden, **more)
        assert p.returncode != 0 and "appearance hidden key" in p.stdout + p.stderr, (name, p.stdout, p.stderr)
        refused += 1
    assert reader(hidden, effect=1).returncode == 0 and reader(hidden, attachment=1).returncode == 0
    print("PASS N3DH client reader: the hidden keys read; %d malformed files refused (flags, tables before 44, "
          "keys 0, past the file, itself, twice, 17, a hiding key hidden, nothing hidden, a hidden key with an "
          "effect or attachment, truncated, trailing)" % refused, flush=True)


def nothing_hidden(hidden):
    """`hidden` (key 1 hides key 2) with entry 1's hidden keys removed: an
    N3DH whose entries hide nothing."""
    at = len(render_detail.serialize(**dict(ARGS, appearances=()))) + 4  # N3D1's bytes plus the flags
    # The appearance count, entry 1's two replacements (1, 2), its one hidden key (2).
    assert hidden[at:at + 24] == u(2) + u(2) + u(1) + u(2) + u(1) + u(2), hidden[at:at + 24]
    return hidden[:at + 16] + u(0) + hidden[at + 24:]


def package(hidden):
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
        (root / "detail.bin").write_bytes(hidden)
        (root / "package.json").write_text(json.dumps(m))
        main.cook(root, out)
        assert (out / "render-detail.bin").read_bytes() == hidden

        def check(good=True, client_only=False):
            commands = [[str(CHECK), str(out)]]
            if not client_only:
                commands.append(["target/debug/n3e-server", "--check-content"])
            results = [subprocess.run(c, env={**os.environ, "N3E_PACKAGE": str(out)}, capture_output=True, text=True)
                       for c in commands]
            for r in results:
                assert (r.returncode == 0) == good, (r.stdout[-400:], r.stderr[-400:])
            if good and not client_only:
                assert results[1].stdout.splitlines()[0] in results[0].stdout.splitlines()
            return results

        client = check()[0].stdout.splitlines()
        assert "detail hides key=1 keys=2" in client, client

        files = {p.name: p.read_bytes() for p in out.iterdir() if p.name not in ("release.bin", "release.sha256")}

        def repack(changes):
            changed = {**files, **changes}
            index = b"N3R1" + u(1) + u(m["engine_version"]) + u(m["protocol_version"]) + string(m["game_id"]) \
                + string(m["package_version"]) + u(len(changed))
            for name, data in sorted(changed.items()):
                (out / name).write_bytes(data)
                index += string(name) + u(len(data)) + digest(data)
            (out / "release.bin").write_bytes(index)

        repack({"render-detail.bin": flags(hidden, 3)})
        check(False, True)  # the client reads the flags; the server only the projection
        repack({"render-detail.bin": b"N3DZ" + hidden[4:]})
        check(False)  # both refuse an unknown magic
        (root / "detail.bin").write_bytes(flags(hidden, 1))
        try:
            main.cook(root, Path(tmp) / "refused")
        except ValueError as error:
            assert "render detail layout flags" in str(error), error
        else:
            raise AssertionError("cooked N3DH without the hidden-key flag")
    print("PASS N3DH package: both readers take an engine 29 package whose key 1 hides key 2 (the client reports "
          "it), the client refuses bad flags the server does not read, both refuse an unknown magic, the cook "
          "refuses flags without 4 or 8", flush=True)


hidden = serializer()
client_reader(hidden)
package(hidden)
