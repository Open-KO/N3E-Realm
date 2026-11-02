"""RQ-078 (make test): the realm's front-end client choice (spec 11 "The client
choice", content/front-end.md "Choosing the client"). No KO data: the Moradon
package's own realm-config.json and front-ends.json are checked against an
empty stand-in for each input tree, and every refusal runs on a synthetic
package written here.

- Moradon's catalogue is well formed, each recipe names the five screens, and
  its configured choice resolves to its recipe once the inputs exist.
- A choice the package does not offer is refused, naming the ones it does; so
  are a missing or malformed realm-config.json, an unknown key, and a choice
  whose input tree is missing, naming the tree and how to get it.
- A malformed catalogue is refused: a bad client id, a recipe outside the
  package or missing, an absolute or escaping tree, missing or extra keys.

The live half (each offered choice cooks twice the same and the client loader
takes it) is tests/front_end_live.py, which needs the KO tree."""
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/assetc"))
import front_end_choice as choice  # noqa: E402
import ko_front_end  # noqa: E402

MORADON = ROOT / "games/moradon"

# --- the Moradon package's own choice -----------------------------------------
offered = choice.catalogue(MORADON)
assert offered, "Moradon offers no front end"
for client, entry in offered.items():
    recipe = json.loads((MORADON / entry["recipe"]).read_text())
    assert set(recipe["screens"]) == set(ko_front_end.SCREENS), (client, sorted(recipe["screens"]))
configured = json.loads((MORADON / choice.CONFIG).read_text())["front_end"]
assert configured == "1097", "the realm's default front end is 1097's (Q71)"
with tempfile.TemporaryDirectory(prefix="n3e-front-end-choice-") as td:
    stand_in = pathlib.Path(td)
    for item in offered[configured]["inputs"]:
        (stand_in / item["tree"]).mkdir(parents=True, exist_ok=True)
    chosen = choice.choose(MORADON, stand_in)
    assert chosen["client"] == "1097" and chosen["recipe"] == MORADON / "front-end.json", chosen
    assert chosen["inputs"] == [stand_in / "assets/ko"], chosen
    for client in offered:
        for item in offered[client]["inputs"]:
            (stand_in / item["tree"]).mkdir(parents=True, exist_ok=True)
        assert choice.resolve(MORADON, client, stand_in)["client"] == client
print("PASS front-end choice: Moradon offers %s and chooses %s" % (", ".join(sorted(offered)), configured))

# --- refusals on synthetic packages ---------------------------------------------
CATALOGUE = {"1097": {"recipe": "front-end.json", "inputs": [{"tree": "trees/a", "get": "make a-tree"}]},
             "1298": {"recipe": "front-end-1298.json", "inputs": [{"tree": "trees/b", "get": "make b-tree"}]}}


def package(base, config=None, catalogue=None, recipes=("front-end.json", "front-end-1298.json"), trees=("trees/a",)):
    game = base / "game"
    game.mkdir()
    if config is not None:
        (game / choice.CONFIG).write_text(config if type(config) is str else json.dumps(config))
    (game / choice.CATALOGUE).write_text(json.dumps(CATALOGUE if catalogue is None else catalogue))
    for name in recipes:
        (game / name).write_text("{}")
    for tree in trees:
        (base / tree).mkdir(parents=True)
    return game


def refused(expect, **kw):
    with tempfile.TemporaryDirectory(prefix="n3e-front-end-choice-") as td:
        base = pathlib.Path(td)
        game = package(base, **kw)
        try:
            chosen = choice.choose(game, base)
        except choice.Refused as error:
            assert expect in str(error), (expect, str(error))
            return str(error)
        raise AssertionError("not refused (%s): %r" % (expect, chosen))


with tempfile.TemporaryDirectory(prefix="n3e-front-end-choice-") as td:
    base = pathlib.Path(td)
    game = package(base, config={"front_end": "1097"})
    assert choice.choose(game, base) == dict(client="1097", recipe=game / "front-end.json", inputs=[base / "trees/a"])

messages = [
    refused("front end '2145' is not one this package cooks; it cooks 1097, 1298", config={"front_end": "2145"}),
    refused("front end '1298' needs trees/b, which is missing on this machine: make b-tree", config={"front_end": "1298"}),
    refused("realm-config.json: missing (the realm's choices"),
    refused("realm-config.json: not JSON", config="{front_end: 1097"),
    refused("realm-config.json: not a JSON object", config="[]"),
    refused("unknown key frontend", config={"frontend": "1097"}),
    refused("front_end must name a KO client, one of 1097, 1298", config={"front_end": 1097}),
    refused("front_end must name a KO client", config={}),
    refused("front-ends.json: offers no front end", config={"front_end": "1097"}, catalogue={}),
    refused("is not a client id", config={"front_end": "1097"}, catalogue={"KO 1097": CATALOGUE["1097"]}),
    refused("1097 needs exactly inputs, recipe", config={"front_end": "1097"},
            catalogue={"1097": dict(CATALOGUE["1097"], title="x")}),
    refused("recipe must be a .json file beside it", config={"front_end": "1097"},
            catalogue={"1097": dict(CATALOGUE["1097"], recipe="../front-end.json")}),
    refused("1097's recipe", config={"front_end": "1097"}, recipes=()),
    refused("needs 1 to 4 inputs", config={"front_end": "1097"}, catalogue={"1097": dict(CATALOGUE["1097"], inputs=[])}),
]
for tree in ("/abs/tree", "trees/../a", "trees//a", "trees\\a", ""):
    messages.append(refused("inputs are each a repository-relative tree", config={"front_end": "1097"},
                            catalogue={"1097": dict(CATALOGUE["1097"], inputs=[{"tree": tree, "get": "x"}])}))
messages.append(refused("inputs are each a repository-relative tree", config={"front_end": "1097"},
                        catalogue={"1097": dict(CATALOGUE["1097"], inputs=[{"tree": "trees/a"}])}))
# An offered choice is refused through resolve too, before any cook reads it.
with tempfile.TemporaryDirectory(prefix="n3e-front-end-choice-") as td:
    base = pathlib.Path(td)
    game = package(base, config={"front_end": "1097"})
    try:
        choice.resolve(game, "steam", base)
        raise AssertionError("resolve took a client the package does not offer")
    except choice.Refused as error:
        assert "front end 'steam' is not one" in str(error), str(error)
print("PASS front-end choice: %d refusals, each naming what to change" % (len(messages) + 1))
