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
  player does.

A race whose model the reader still refuses is listed in OPEN with the
refusal and the item that reads KO's handling of it; the test fails when the
refusal changes or the race cooks, so the list stays true.
"""
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "tools/assetc"))
import ko_character  # noqa: E402
import ko_player  # noqa: E402
import main  # noqa: E402

TREE = pathlib.Path("assets/ko")
OUT = pathlib.Path("build/ko-player-races")
# Races the reader refuses today: (the refusal, what is open).
OPEN = {
    1: ("past four joint influences", "49 lower-part vertices with five joint influences, which the player's "
        "N3S1 scenes do not carry (PQ-280)"),
    12: ("animation metadata", "clip 93 (breath_CrossBow0) at 0 frames a second (KO's handling unread)"),
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
        ko_character.convert(TREE, ko_player.SOURCE, out / "idle", 0, 1.0, definition=definition)
        main.cook(out / "idle", out / "cooked-idle")
        assert (out / "cooked-idle/scene.bin").read_bytes()[:4] == b"N3S1"
    except ValueError as error:
        assert race in OPEN, (race, str(error))
        assert OPEN[race][0] in str(error), (race, str(error), OPEN[race])
        refused.append(race)
        continue
    assert race not in OPEN, "race %d now cooks: drop it from OPEN" % race
    cooked.append(race)
    print("PASS race %d (%s): %d parts, %d part files over its faces and hairs, %d clips, idle cooks"
          % (race, entry["looks"], len(positions), len(names), len(clips)))
assert sorted(refused) == sorted(OPEN), (refused, OPEN)
for race in refused:
    print("OPEN race %d: %s" % (race, OPEN[race][1]))
print("PASS ko_player_races: races %s cook; %s open" % (cooked, refused))
