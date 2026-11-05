"""RQ-003: every race the package's create offers has a KO player model.

games/moradon/character-create.json names each race's `looks` (the stem of its
UPC_DefaultLooks parts) and `player`, the race of the package's player scenes.
With the pinned client tree (assets/ko; SKIP without it), for every race:

- tools/assetc/ko_player.py reads the race's looks row (KO's key is the race
  code), checks its parts are the race's `looks`, and keeps the parts KO sets
  (an empty name sets none: the Wrinkle Tuarek has no lower part and no hair);
- every face (00..faces-1) and, where the race has hair, every hair
  (00..hairs-1) the create screen reaches is a part file whose texture and
  skin read and whose render state the player path draws;
- every clip the player cook converts (ko_player.clip_indices, all states) is
  in the race's clip table;
- its idle model converts and cooks, face 0 and hair 0, as the package's
  player does: N3S1, or N3SI (engine 43, RQ-163) for a race with a drawn
  vertex past four joint influences, which keeps every influence as KO's
  skinning sums them (the Arch Tuarek: 49 lower-part vertices with five);
- its render detail (tools/assetc/ko_detail.py, face 0 and hair 0, no world)
  cooks with each of its parts also worn as a 1298 appearance part
  (ko_appearance.part_levels): N3D2, or N3DI (engine 44, RQ-164) when a drawn
  vertex has more than four influences, kept in the influence tables of the
  body's level 0 and of each key that wears such a part.

A race whose model the reader still refuses is listed in OPEN with the
refusal and the item that reads KO's handling of it; the test fails when the
refusal changes or the race cooks, so the list stays true.

RQ-158: every race of `models.create` has its create model in front-end.bin
(N3FE version 24): its create model (tools/assetc/ko_front_end.py
create_model, KO's InitChr and SetChr parts, breathing) cooks N3S1 or N3SM,
as a front-end model record holds; RQ-174 (version 27): without its face and
hair, which follow it as parts on its skeleton, the rules' faces and hairs
(none for a race without hair, the Wrinkle Tuarek). A race outside it is
listed in UNSHIPPED with why: the front-end record's refusal for a race whose
model has a drawn vertex past four influences (RQ-165), or none for a race
that cooks but whose create screen the realm does not draw yet.

RQ-176 (version 29): each shipped create model also cooks in its
specialties' create dress from the pinned tree's own 1298 table
(ko_create.dress, Q106), each specialty drawn: the dress the most specialties
wear as the model's own parts, the others' parts after it, each plug on its
looks row joint.
"""
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "tools/assetc"))
import ko_character  # noqa: E402
import ko_create  # noqa: E402
import ko_detail  # noqa: E402
import ko_front_end  # noqa: E402
import ko_player  # noqa: E402
import main  # noqa: E402

TREE = pathlib.Path("assets/ko")
OUT = pathlib.Path("build/ko-player-races")
# Races the reader refuses today: (the refusal, what is open).
OPEN = {}
# RQ-158: convertible races whose create model the package does not ship:
# (the front-end cook's refusal or None, why).
UNSHIPPED = {
    1: ("front-end model magic", "its create model is N3SI, which a front-end record does not hold (RQ-165)"),
    11: (None, "El Morad: the realm's create is Karus until nation select (RQ-006)"),
    12: ("front-end model magic", "its create model is N3SI, which a front-end record does not hold (RQ-165)"),
    13: (None, "El Morad: the realm's create is Karus until nation select (RQ-006)"),
}

if not (TREE / "Data/UPC_DefaultLooks.tbl.csv").is_file():
    print("SKIP ko_player_races: no pinned client tree at assets/ko (make ko-assets)")
    sys.exit(0)

rules = ko_player.rules()
assert rules["player"] in rules["content"], rules
assets = ko_character.Assets(TREE)
every = ko_player.clip_indices(True, True, True, True)
cooked, refused = [], []
for entry in rules["races"]:
    race = entry["race"]
    looks = ko_player.looks(assets, entry)
    positions = looks["positions"]
    if race == 3:  # the contract's Wrinkle Tuarek: no lower part, no hair
        assert positions == ["upper", "face", "hands", "feet"], positions
    else:
        assert positions == list(ko_player.POSITIONS), (race, positions)
    variants = [ko_player.looks(assets, entry, face=n)["definition"]["parts"] for n in range(rules["faces"])]
    if "hair" in positions:
        variants += [ko_player.looks(assets, entry, hair=n)["definition"]["parts"] for n in range(rules["hairs"])]
    names = sorted({p for parts in variants for p in parts}, key=str.lower)
    for name in names:
        part = ko_character.part(assets.get(name))
        assert part["render_state"] == ko_character.OPAQUE_STATE, (race, name, part["render_state"])
        w, h, pixels = ko_character.texture(assets.get(part["texture"]))
        assert min(pixels[3::4]) == 255, (race, name, "alpha the player path does not draw")
        ko_character.skins(assets.get(part["skin"]), every=True)
    try:
        definition = looks["definition"]
        clips = ko_character.animations(assets.get(definition["animation"]))
        missing = [(s, i) for s, i in every if i >= len(clips)]
        assert not missing, (race, missing)
        out = OUT / str(race)
        report = ko_character.convert(TREE, ko_player.SOURCE, out / "idle", 0, 1.0, definition=definition)
        main.cook(out / "idle", out / "cooked-idle", influences=True)
        many = report.get("many_influences")
        magic = (out / "cooked-idle/scene.bin").read_bytes()[:4]
        assert magic == (b"N3SI" if many else b"N3S1"), (race, magic, many)
        # RQ-164: render detail with each part also worn as an appearance part.
        rows = [dict(item="test:part/%d" % i, slot=i, source=name, parts=[i])
                for i, name in enumerate(definition["parts"])]
        detail, detail_report = ko_detail.cook(TREE, dict(atlas=None), definition, rows)
        tables = detail_report.get("many_influences")
        assert detail[:4] == (b"N3DI" if many else b"N3D2"), (race, detail[:4], tables)
        assert bool(tables) == bool(many), (race, tables, many)
        if tables:
            # Each part's corners past four influences, at each of its four LODs.
            past = []
            for name in definition["parts"]:
                _, lods = ko_character.skins(assets.get(ko_character.part(assets.get(name))["skin"]), every=True)
                past.append([sum(1 for v in lod["indices"] if len(lod["joints"][v]) > 4) for lod in lods])
            assert tables["levels"] == [sum(p[k] for p in past) for k in range(4)], (race, tables, past)
            assert tables["appearances"] == {i + 1: p for i, p in enumerate(past) if any(p)}, (race, tables, past)
            assert tables["most"] == many["most"], (race, tables, many)
    except ValueError as error:
        assert race in OPEN, (race, str(error))
        assert OPEN[race][0] in str(error), (race, str(error), OPEN[race])
        refused.append(race)
        continue
    assert race not in OPEN, "race %d now cooks: drop it from OPEN" % race
    cooked.append(race)
    # RQ-158: its create model, as front-end.bin carries it.
    shipped = race in rules["models"]["create"]
    assert shipped != (race in UNSHIPPED), (race, "models.create and UNSHIPPED disagree")
    try:
        made = []
        record = ko_front_end.create_model(assets, race, OUT / str(race) / "create", entry, rules["faces"],
                                           rules["hairs"], made)
        create_magic = record[4:8]
        assert create_magic in (b"N3S1", b"N3SM"), (race, create_magic)
        assert made == [dict(race=race, faces=rules["faces"], hairs=rules["hairs"] if "hair" in positions else 0,
                             bytes=len(record))], (race, made)
        assert shipped or UNSHIPPED[race][0] is None, (race, "now cooks a create model", UNSHIPPED[race])
    except ValueError as error:
        assert not shipped and UNSHIPPED[race][0] and UNSHIPPED[race][0] in str(error), (race, str(error))
        record, create_magic = None, None
    if shipped:
        # RQ-176: dressed from the 1298 table, as the 1298 front end's cook.
        tree_inputs = ko_front_end.Inputs([assets])
        dress = ko_create.dress(ko_create.plan(ko_player.GAME, "1298", {}), tree_inputs, {race})[race]
        dressed = []
        dressed_record = ko_front_end.create_model(
            assets, race, OUT / str(race) / "create-dressed", entry, rules["faces"], rules["hairs"], dressed, dress,
            tree_inputs, ko_front_end.Textures(tree_inputs))
        worn = dressed[0]["dresses"]
        assert set(worn) == set(entry["specialties"]) and sum(d["body"] for d in worn.values()) >= 1, (race, worn)
        assert dressed[0]["bytes"] == len(dressed_record), (race, dressed[0])
        print("PASS race %d create dress (1298's table): %s, %d dress parts, %d bytes" % (
            race, ", ".join("%d: %s, %d plugs" % (s, "its own parts" if d["body"] else "%d parts" % len(d["parts"]),
                                                  len(d["plugs"])) for s, d in worn.items()),
            dressed[0]["dress_parts"], len(dressed_record)))
    print("PASS race %d create model: %s" % (race, "%s, %d faces, %d hairs, %d bytes in front-end.bin" % (
        create_magic.decode(), made[0]["faces"], made[0]["hairs"], len(record)) if shipped
        else "not shipped: " + UNSHIPPED[race][1]))
    print("PASS race %d (%s): %d parts, %d part files over its faces and hairs, %d clips, idle cooks (%s%s), "
          "render detail with its parts worn cooks (%s%s)"
          % (race, entry["looks"], len(positions), len(names), len(clips), magic.decode(),
             ": %(vertices)d drawn vertices past four influences, at most %(most)d" % many if many else "",
             detail[:4].decode(), ": %d corners past four in level 0 and in keys %s"
             % (tables["levels"][0], sorted(tables["appearances"])) if tables else ""))
assert sorted(refused) == sorted(OPEN), (refused, OPEN)
for race in refused:
    print("OPEN race %d: %s" % (race, OPEN[race][1]))
print("PASS ko_player_races: races %s cook; %s open" % (cooked, refused))
