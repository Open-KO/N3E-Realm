"""RQ-203 (Q120): the world's dust overlay on worn items, cooked into N3E6.

KO's world durability setter (1298 0045d5f0, 1097 004535a0; the source's
CPlayerBase::DurabilitySet) puts Misc\\Dust_Hard.dxt on a worn hand plug or
armour part below 31 % of its item's durability and Misc\\Dust_Soft.dxt below
71 % (specs/KO-FINDINGS.md 8.6). On original synthetic bytes (PQ-211's N3EF
textures and clips), with no KO data:

- appearance_effects.n3e6 writes N3E5 with an optional sort section and the
  dust section (two of the file's textures, 1-16 keys), and refuses a texture
  past the file, a key out of range or twice, and no or 17 keys; the client's
  reader (build/client/n3e-effects-check) takes the file, reports its dust,
  and refuses malformed ones (truncation, trailing bytes, a texture past the
  file, a duplicate key, a count of 0 or 17, a dust section under N3E5).
- ko_fx_bake.dust_keys takes the rows a KO durability setter dusts: hand plugs
  and armour parts.
- realm-config.json's `world_dust` is `none` (the default) or `draw`, any other
  value refused by name; the Moradon package keeps `none`, so its package is
  unchanged (the hosted look is the maintainer's choice).

With the pinned KO tree (assets/ko; SKIP without it) ko_fx_bake.cook writes
the two textures from the tree into an N3E6 the client reads.
"""
import json
import pathlib
import struct
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/assetc"))
sys.path.append(str(ROOT / "tests"))
import appearance_effects  # noqa: E402
import front_end_choice  # noqa: E402
import ko_fx_bake  # noqa: E402
from appearance_effects_live import n3ef as synthetic  # noqa: E402

CHECK = ROOT / "build/client/n3e-effects-check"


def refused(call, text):
    try:
        call()
    except ValueError as error:
        assert text in str(error), (text, str(error))
        return
    raise AssertionError("not refused: " + text)


def read(data):
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "effects.bin"
        path.write_bytes(data)
        return subprocess.run([str(CHECK), str(path)], capture_output=True, text=True)


def main():
    n3ef = synthetic()  # five textures, three clips, no bindings
    dust = dict(hard=1, soft=2, keys=[2, 1])
    good = appearance_effects.n3e6(n3ef, [], [], [], [], dust, 2)
    assert good[:4] == b"N3E6" and good.endswith(struct.pack("<5I", 1, 2, 2, 2, 1)), good[-24:]
    # The empty glow, rule and sort sections precede it.
    assert good[-32:-20] == struct.pack("<3I", 0, 0, 0), good[-32:]
    for bad, keys, text in [(dict(dust, hard=5), 2, "appearance dust texture"),
                            (dict(dust, soft=-1), 2, "appearance dust texture"),
                            (dict(dust, keys=[0]), 2, "appearance dust key"),
                            (dict(dust, keys=[3]), 2, "appearance dust key"),
                            (dict(dust, keys=[1, 1]), 2, "appearance dust key"),
                            (dict(dust, keys=[]), 2, "count out of bounds"),
                            (dict(dust, keys=list(range(1, 18))), 17, "count out of bounds")]:
        refused(lambda: appearance_effects.n3e6(n3ef, [], [], [], [], bad, keys), text)
    refused(lambda: appearance_effects.n3e6(b"N3E5" + n3ef[4:], [], [], [], [], dust, 2), "N3EF required")
    print("PASS N3E6 serializer: two of the file's textures and 1-16 appearance keys each once, after empty "
          "glow, rule and sort sections; its refusals", flush=True)

    p = read(good)
    assert p.returncode == 0 and "dust=1,2 dust_keys=2,1" in p.stdout, (p.stdout, p.stderr)
    section = len(good) - 20
    malformed = [
        (good + b"\0", "cooked trailing bytes"),
        (good[:-1], "truncated cooked data"),
        (good[:section] + struct.pack("<I", 5) + good[section + 4:], "appearance dust texture"),
        (good[:section + 4] + struct.pack("<I", 9) + good[section + 8:], "appearance dust texture"),
        (good[:-4] + struct.pack("<I", 2), "duplicate appearance dust key"),
        (good[:section + 8] + struct.pack("<I", 0), "cooked count"),
        (good[:section + 8] + struct.pack("<I", 17) + struct.pack("<17I", *range(1, 18)), "cooked count"),
        (good[:-4] + struct.pack("<I", 0), "cooked count"),
        (b"N3E5" + good[4:], "cooked count"),  # N3E5 needs a sort record
    ]
    for i, (data, reason) in enumerate(malformed):
        p = read(data)
        assert p.returncode != 0 and reason in p.stderr, (i, reason, p.stdout, p.stderr)
    print(f"PASS the client reads N3E6's dust and refuses {len(malformed)} malformed files", flush=True)

    rows = [dict(item="a", slot=0, source="Item/1_2011_00_0.n3cplug", joint=12),
            dict(item="b", slot=4, source="Item/2_4102_10_0.N3CPart", parts=[0]),
            dict(item="c", slot=5, source="Item/x.n3cpart"),
            dict(item="d", slot=1, chrplug_2145="Item/1_7025_00_0.n3chrplug"),
            dict(item="e", slot=1, source="Item/1_7025_00_0.n3cplug", joint=5)]
    assert ko_fx_bake.dust_keys(rows) == [1, 2, 5], ko_fx_bake.dust_keys(rows)
    moradon = json.loads((ROOT / "games/moradon/appearance.json").read_text())
    assert ko_fx_bake.dust_keys(moradon) == list(range(1, len(moradon) + 1)), moradon
    print("PASS dust keys: hand plug and armour part rows, the Moradon package's every row", flush=True)

    assert "world_dust" in front_end_choice.CONFIG_KEYS
    with tempfile.TemporaryDirectory() as tmp:
        game = pathlib.Path(tmp)
        for config, drawn in [({"front_end": "x"}, False), ({"world_dust": "none"}, False),
                              ({"world_dust": "draw"}, True)]:
            (game / front_end_choice.CONFIG).write_text(json.dumps(config))
            assert front_end_choice.world_dust(game) is drawn, config
        for value in ("Draw", 1, None, ["draw"]):
            (game / front_end_choice.CONFIG).write_text(json.dumps({"world_dust": value}))
            try:
                front_end_choice.world_dust(game)
            except front_end_choice.Refused as error:
                assert "world_dust must be one of none, draw" in str(error), error
            else:
                raise AssertionError(value)
            # choose() refuses it too, before the catalogue is read.
            try:
                front_end_choice.choose(game)
            except front_end_choice.Refused as error:
                assert "world_dust must be one of none, draw" in str(error), error
            else:
                raise AssertionError(value)
    assert front_end_choice.world_dust(ROOT / "games/moradon") is False
    print("PASS realm-config.json world_dust: none (default) or draw, others refused; Moradon keeps none",
          flush=True)

    tree = ROOT / "assets/ko"
    if not (tree / "Misc").is_dir():
        print("SKIP the KO cook: no pinned client tree at assets/ko (make ko-assets)", flush=True)
        return
    import ko_character
    definition = json.loads((ROOT / "games/moradon/effects.json").read_text())
    first = next(iter(definition["clips"]))
    definition = dict(clips={first: definition["clips"][first]}, bindings=[])
    with tempfile.TemporaryDirectory() as tmp:
        out = pathlib.Path(tmp) / "effects.bin"
        report = ko_fx_bake.cook(ko_character.Assets(tree), definition, out, keys=5, dust=[1, 2, 3, 4, 5])
        data = out.read_bytes()
        assert data[:4] == b"N3E6" and report["dust"] == dict(textures=list(ko_fx_bake.DUST), keys=[1, 2, 3, 4, 5])
        textures = report["textures"]
        assert data.endswith(struct.pack("<8I", textures - 2, textures - 1, 5, 1, 2, 3, 4, 5)), data[-32:]
        p = subprocess.run([str(CHECK), str(out)], capture_output=True, text=True)
        assert p.returncode == 0 and f"dust={textures - 2},{textures - 1} dust_keys=1,2,3,4,5" in p.stdout, p
        plain = pathlib.Path(tmp) / "plain.bin"
        ko_fx_bake.cook(ko_character.Assets(tree), definition, plain, keys=5)
        assert plain.read_bytes()[:4] == b"N3EF"
    print(f"PASS the KO cook writes {', '.join(ko_fx_bake.DUST)} from the pinned tree into an N3E6 the client "
          "reads; without dust keys the file is as before", flush=True)


if __name__ == "__main__":
    main()
