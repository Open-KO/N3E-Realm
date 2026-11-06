"""RQ-199: the world's lower under a robe (tools/assetc/ko_appearance.cook).

KO's world releases the lower part while the upper item is a robe: 1298's
player part set (00467d50) and its other players' (0045cd90), and 1097's
player part set (00459c60), set part 1 to the empty name, which
CN3Chr::PartSet (1298 0041b6d0, 1097 00447a70) takes as a release, so the
player draws no lower at all (specs/KO-FINDINGS.md 8.7). On original synthetic
bytes (tests/ko_armour_2145.py's part and skin), with no KO data:

- an upper part row with `"robe": true` replaces the player model's lower
  body parts as well as its own (the robe's N3D2 entry suppresses the looks
  lower), and reports which; a race with no lower part replaces the upper
  alone; `robe` false or absent cooks as before, byte for byte;
- the hall reads the same row as a robe (ko_front_end.hall_keys);
- a robe on a plug, a 2145 part or skeletal plug, a lower row or a row over
  two part positions, a robe that is not a bool, a robe without the part
  positions and positions that do not match the body parts are refused;
- RQ-207: a robe beside an ordinary lower part row hides it (KO's world draws
  no worn lower under a robe): the robe's report lists the lower keys, in
  either order, and its render detail is N3DH with them (N3D2's bytes plus
  the layout flags and each entry's hidden keys); a row that draws on the
  lower and elsewhere, or a 2145 lower part, beside a robe is refused; the
  lower row without a robe cooks as before.
"""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/assetc"))
import ko_appearance  # noqa: E402
import ko_armour_2145 as ko_armour_2145_module  # noqa: E402
import ko_front_end  # noqa: E402
import render_detail  # noqa: E402

# tests/ko_armour_2145.py's synthetic part and skin (its name is also the cook's).
_spec = importlib.util.spec_from_file_location("ko_armour_2145_test", ROOT / "tests/ko_armour_2145.py")
_fixtures = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixtures)
Files, part_file, refused, skin_file = _fixtures.Files, _fixtures.part_file, _fixtures.refused, _fixtures.skin_file

POSITIONS = ["upper", "lower", "face", "hands", "feet", "hair"]
BODY = [1, 2, 3, 4, 5, 6]  # each body part's texture slot
WORLD = [[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]]]
PIXEL = [(1, 1, b"\0\0\0\xff")]


def cook(rows, positions=POSITIONS, body=BODY):
    textures = [PIXEL] * (1 + len(body))
    return ko_appearance.cook(FILES, rows, WORLD, textures, body, positions)


def row(**change):
    return dict(dict(item="demo:item/robe", slot=4, source="p.n3cpart", parts=[0]), **change)


real = ko_appearance.ko_tiles.mip_chains
ko_appearance.ko_tiles.mip_chains = lambda data, skip=0: [PIXEL]
try:
    FILES = Files(**{"p.n3cpart": part_file(), "item\\t.n3cskins": skin_file([(0, 0, 1)] * 3), "item\\t.dxt": b""})
    plain = cook([row()])
    appearances, states, reports, _ = cook([row(robe=True)])
    assert appearances[0][0] == [1, 2], appearances[0][0]
    assert reports[0]["robe"] == dict(bare=[1], hides=[]), reports[0]
    assert appearances[0][1] == plain[0][0][1] and states == plain[1], "a robe's own mesh and state are its part's"
    assert plain[0][0][0] == [1] and "robe" not in plain[2][0], plain[2][0]
    assert cook([row(robe=False)]) == plain, "robe false cooks as no robe"
    assert ko_appearance.cook(FILES, [row()], WORLD, [PIXEL] * 7, BODY) == plain, "no positions, no robe: as before"

    def detail(appearances, **more):
        return render_detail.serialize(view=[1.134464, .5, 256], thresholds=[[6, 18, 32, 128]] * 4,
                                       workload=[30, 60, 100], world_count=1, textures=[PIXEL] * 8, radius=1,
                                       levels=[appearances[0][1][0]] * 4, appearances=appearances, **more)
    robe, before = detail(appearances), detail(plain[0])
    assert robe[:4] == before[:4] == b"N3D2" and len(robe) == len(before) + 4, (len(robe), len(before))

    # The Wrinkle Tuarek's looks have no lower part: a robe replaces the upper alone.
    tuarek = ["upper", "face", "hands", "feet"]
    appearances, _, reports, _ = cook([row(robe=True)], tuarek, BODY[:4])
    assert appearances[0][0] == [1] and reports[0]["robe"] == dict(bare=[], hides=[]), (appearances[0][0], reports[0])

    # The hall reads the same row as a robe (its lower then the looks lower, 005fc6f0).
    keys = ko_front_end.hall_keys(dict(rows=[row(robe=True)], race=1, positions=POSITIONS), {})
    assert keys[0]["robe"] is True, keys

    what = "appearance key 1 (demo:item/robe, slot 4)"
    refused(lambda: cook([row(robe=True, joint=12, source="x.n3cplug")]), what + ": a robe is an upper part's")
    refused(lambda: cook([row(robe=True, part_2145="k.n3cpart")]), "a robe is an upper part's")
    refused(lambda: cook([row(robe=True, chrplug_2145="Item/b.n3chrplug")]), "a robe is an upper part's")
    refused(lambda: cook([row(robe=True, parts=[1])]), "its parts all the upper")
    refused(lambda: cook([row(robe=True, parts=[0, 1])]), "its parts all the upper")
    refused(lambda: cook([row(robe=True, parts=[])]), "its parts all the upper")
    refused(lambda: cook([row(robe=True, parts=[6])]), "its parts all the upper")
    refused(lambda: cook([row(robe="yes")]), what + " robe: true or false")
    refused(lambda: cook([row(robe=1)]), " robe: true or false")
    refused(lambda: cook([row(robe=True)], None), "a robe needs the player model's part positions")
    refused(lambda: cook([row()], POSITIONS[:5]), "5 part positions for 6 body parts")

    lower = dict(item="demo:item/legs", slot=5, source="p.n3cpart", parts=[1])
    assert cook([lower])[0][0][0] == [2]
    assert [a[0] for a in cook([row(), lower])[0]] == [[1], [2]]
    assert "robe" not in cook([row(), lower])[2][0]
    # RQ-207: the robe hides the worn lower, in either order; its own entry
    # still replaces the looks lower.
    appearances, states, reports, _ = cook([row(robe=True), lower])
    assert [a[0] for a in appearances] == [[1, 2], [2]] and reports[0]["robe"] == dict(bare=[1], hides=[2]), reports
    assert "robe" not in reports[1], reports[1]
    hidden = detail(appearances, hides=[r.get("robe", {}).get("hides", []) for r in reports])
    unhidden = detail(appearances)
    assert hidden[:4] == b"N3DH" and unhidden[:4] == b"N3D2", (hidden[:4], unhidden[:4])
    # N3DH: N3D2's bytes with the layout flags (4: hidden keys alone) after
    # the projection and each entry's hidden keys after its replacements.
    assert len(hidden) == len(unhidden) + 4 + 4 * 2 + 4, (len(hidden), len(unhidden))
    assert hidden[16:20] == render_detail.u(4) and hidden[4:16] == unhidden[4:16], hidden[:20]
    assert render_detail.layout(hidden[:20]) == 4 and not render_detail.has_tables(hidden[:20])
    appearances, _, reports, _ = cook([lower, row(robe=True)])
    assert reports[1]["robe"] == dict(bare=[1], hides=[1]) and "robe" not in reports[0], reports
    # Two lower rows (each its own slot) are both hidden; a robe alone hides none.
    shorts = dict(lower, item="demo:item/shorts", slot=7)
    assert cook([row(robe=True), lower, shorts])[2][0]["robe"]["hides"] == [2, 3]
    assert cook([row(robe=True)])[2][0]["robe"] == dict(bare=[1], hides=[])
    refused(lambda: cook([row(robe=True), dict(lower, parts=[1, 3])]),
            "appearance key 2 (demo:item/legs) draws on the lower, which KO's world leaves bare under a robe "
            "(key 1), and elsewhere; n3e hides a whole key")
    real_source = ko_armour_2145_module.source
    ko_armour_2145_module.source = lambda install=None: FILES
    try:
        refused(lambda: cook([row(robe=True), dict(item="demo:item/krowaz_lower", slot=5, part_2145="p.n3cpart",
                                                   parts=[1])]),
                "appearance key 2 (demo:item/krowaz_lower) draws on the lower, which KO's world leaves bare under a "
                "robe (key 1); it is a 2145 part, whose part set under a robe (2233's) is unread")
    finally:
        ko_armour_2145_module.source = real_source
    # A plug and a part elsewhere sit beside a robe.
    feet = dict(item="demo:item/boots", slot=6, source="p.n3cpart", parts=[4])
    assert [a[0] for a in cook([row(robe=True), feet])[0]] == [[1, 2], [5]]
    assert cook([row(robe=True), feet])[2][0]["robe"]["hides"] == []

    # render_detail.serialize's hidden keys: one list per entry, keys of the
    # file, none itself or twice, at most 16, a hiding key hidden by none.
    three = [appearances[0]] * 3
    assert detail(three, hides=[[], [], []]) == detail(three), "no hidden key keeps the bytes"
    assert detail(three, hides=None) == detail(three)
    for bad, why in [([[2]], "appearance hidden key count"), ([[2], [], [], []], "appearance hidden key count"),
                     ([[1], [], []], "appearance key 1 hidden keys"), ([[4], [], []], "appearance key 1 hidden keys"),
                     ([[0], [], []], "appearance key 1 hidden keys"), ([[2, 2], [], []], "appearance key 1 hidden keys"),
                     ([["2"], [], []], "appearance key 1 hidden keys"), ([(2,), [], []], "appearance key 1 hidden keys"),
                     ([[2], [3], []], "appearance key 2 hides keys and is hidden"),
                     ([[2], [1], []], "appearance key 1 hides keys and is hidden")]:
        refused(lambda: detail(three, hides=bad), why)
    many = [appearances[0]] * 18
    refused(lambda: detail(many, hides=[list(range(2, 19))] + [[]] * 17), "appearance key 1 hidden keys")
    assert detail(many, hides=[list(range(2, 18))] + [[]] * 17)[:4] == b"N3DH"
finally:
    ko_appearance.ko_tiles.mip_chains = real
print("PASS world robe (RQ-199): a robe row also replaces the lower body parts (none for a race without one), "
      "other rows cook as before; the hall reads the same robe; a robe off an upper part row, of another "
      "type or without positions, refused; RQ-207: a robe hides each worn lower part (N3DH), a lower row "
      "over another part or a 2145 lower beside a robe refused, bad hidden keys refused", flush=True)
