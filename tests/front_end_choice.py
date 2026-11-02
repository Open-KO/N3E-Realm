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

RQ-084, on synthetic trees and installs written here:

- A choice reads several trees: every input after the first has a unique
  name, and each tree prefix the recipe's paths use (`<name>:<path>`) names
  one of them, or the choice is refused before any cook.
- A reference install (build/ko-reference/<name>/client) is read only when it
  is a pinned one whose manifest names its installer; ko_character.Assets
  then reads each file only when it is the one the manifest lists.
- ko_front_end.Inputs reads an unprefixed path from the first tree and a
  prefixed one from its input; the turn sound (`select.turn_sound`) is the
  first tree's id, or another input's row from its sound.tbl (the pinned
  tree's CSV or a client's encrypted table).

The live half (each offered choice cooks twice the same and the client loader
takes it) is tests/front_end_live.py, which needs the KO tree."""
import hashlib
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/assetc"))
import front_end_choice as choice  # noqa: E402
import ko_character  # noqa: E402
import ko_front_end  # noqa: E402
import ko_installs  # noqa: E402
import ko_tbl  # noqa: E402

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
    assert chosen["inputs"] == [stand_in / "assets/ko"] and chosen["pins"] == [None], chosen
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
    assert choice.choose(game, base) == dict(client="1097", recipe=game / "front-end.json", inputs=[base / "trees/a"],
                                             names=[None], pins=[None])

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

# --- RQ-084: several input trees -----------------------------------------------
PIN = ko_installs.PINNED["installer-1097"]["sha256"]
INSTALL = "build/ko-reference/installer-1097/client"
TWO = {"1097": {"recipe": "front-end.json", "inputs": [
    {"tree": "trees/a", "get": "make a-tree"},
    {"tree": INSTALL, "name": "installer-1097", "get": "unpack the 1097 installer"}]}}
FILES = {"Snd/turn.wav": b"turn", "UI/one.uif": b"one"}


def install(base, sha256=PIN, files=FILES, listed=None, text=None):
    """A synthetic unpack: client/ holds `files`; the manifest names `sha256`
    and lists `listed` (default: every file with its own hash)."""
    root = base / INSTALL
    for name, data in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(data)
    listed = files if listed is None else listed
    manifest = {"sha256": sha256, "manifest": [
        {"path": name, "sha256": hashlib.sha256(data).hexdigest()} for name, data in listed.items()]}
    (root.parent / "manifest.json").write_text(json.dumps(manifest) if text is None else text)


def chosen(recipe=None, catalogue=TWO, **kw):
    """choose() on a synthetic package with the install written by `install(**kw)`."""
    td = tempfile.TemporaryDirectory(prefix="n3e-front-end-inputs-")
    base = pathlib.Path(td.name)
    game = package(base, config={"front_end": "1097"}, catalogue=catalogue, recipes=())
    (game / "front-end.json").write_text(json.dumps(recipe or {}))
    if kw.get("sha256", "") is not None:
        install(base, **{k: v for k, v in kw.items()})
    return td, base, choice.choose(game, base)


def refused_inputs(expect, **kw):
    try:
        td, _, result = chosen(**kw)
        td.cleanup()
    except choice.Refused as error:
        assert expect in str(error), (expect, str(error))
        return str(error)
    raise AssertionError("not refused (%s): %r" % (expect, result))


# A pinned install with its manifest: its tree is the second input, named.
RECIPE = {"screens": {"login": {"ui": "installer-1097:UI/one.uif"}}, "select": {"turn_sound": "installer-1097:7"},
          "music": {"tracks": [{"path": "Snd/a.wav"}]}}
td, base, front = chosen(RECIPE)
assert front["inputs"] == [base / "trees/a", base / INSTALL] and front["names"] == [None, "installer-1097"], front
assert front["pins"][0] is None and front["pins"][1]["installer_sha256"] == PIN, front["pins"]
assert front["pins"][1]["hashes"] == {n.lower(): hashlib.sha256(d).hexdigest() for n, d in FILES.items()}
assert front["pins"][1]["manifest"] == str(base / "build/ko-reference/installer-1097/manifest.json")
td.cleanup()

inputs_refusals = [
    refused_inputs("names input 'installer-2145', which front end '1097' does not have "
                   "(its inputs: installer-1097)", recipe={"intro": {"character": "installer-2145:Intro/x.n3chr"}}),
    refused_inputs("select.turn_sound names input 'b'", recipe={"select": {"turn_sound": "b:2501"}}),
    refused_inputs("music.tracks[1].path names input 'x'",
                   recipe={"music": {"tracks": [{"path": "a.wav"}, {"path": "x:b.wav"}]}}),
    refused_inputs("its one input has no name", recipe={"select": {"hall": "a:hall.n3shape"}},
                   catalogue={"1097": {"recipe": "front-end.json", "inputs": [{"tree": "trees/a", "get": "x"}]}},
                   sha256=None),
    refused_inputs("input %s needs a name" % INSTALL,
                   catalogue={"1097": {"recipe": "front-end.json", "inputs": [
                       TWO["1097"]["inputs"][0], {"tree": INSTALL, "get": "x"}]}}),
    refused_inputs("input name 'KO 1097' is not lower-case",
                   catalogue={"1097": {"recipe": "front-end.json", "inputs": [
                       TWO["1097"]["inputs"][0], dict(TWO["1097"]["inputs"][1], name="KO 1097")]}}),
    refused_inputs("names two inputs b",
                   catalogue={"1097": {"recipe": "front-end.json", "inputs": [
                       dict(TWO["1097"]["inputs"][0], name="b"), dict(TWO["1097"]["inputs"][1], name="b")]}}),
    refused_inputs("inputs are each a repository-relative tree",
                   catalogue={"1097": {"recipe": "front-end.json", "inputs": [
                       dict(TWO["1097"]["inputs"][0], pin="x")]}}, sha256=None),
    # Only a pinned install's client/ is a reference tree a cook reads.
    refused_inputs("build/ko-reference/steam-install is not a pinned reference install",
                   catalogue={"1097": {"recipe": "front-end.json", "inputs": [
                       {"tree": "build/ko-reference/steam-install", "get": "x"}]}}, sha256=None),
    refused_inputs("build/ko-reference/installer-1097 is not a pinned reference install",
                   catalogue={"1097": {"recipe": "front-end.json", "inputs": [
                       {"tree": "build/ko-reference/installer-1097", "get": "x"}]}}, sha256=None),
    refused_inputs("installer-1264/client is not a pinned reference install",
                   catalogue={"1097": {"recipe": "front-end.json", "inputs": [
                       {"tree": "build/ko-reference/installer-1264/client", "get": "x"}]}}, sha256=None),
    # The manifest must exist, be an unpacker's and name the pinned installer.
    refused_inputs("is not the pinned installer-1097 installer's unpack", sha256="0" * 64),
    refused_inputs("is not an unpacker's manifest", text="[]"),
    refused_inputs("is not an unpacker's manifest", text="{not json"),
    refused_inputs("is not an unpacker's manifest", text=json.dumps({"sha256": PIN})),
]
with tempfile.TemporaryDirectory(prefix="n3e-front-end-inputs-") as td:
    base = pathlib.Path(td)
    game = package(base, config={"front_end": "1097"}, catalogue=TWO)
    (base / INSTALL).mkdir(parents=True)
    try:
        choice.choose(game, base)
        raise AssertionError("an install without its manifest was taken")
    except choice.Refused as error:
        inputs_refusals.append(str(error))
        assert "no installer-1097 manifest at" in str(error) and "unpack_installer.py" in str(error), str(error)
print("PASS front-end inputs: a named, pinned second tree resolves; %d refusals" % len(inputs_refusals))

# --- each file read from an install is the one its manifest lists ---------------
with tempfile.TemporaryDirectory(prefix="n3e-front-end-inputs-") as td:
    base = pathlib.Path(td)
    install(base, files={**FILES, "Snd/extra.wav": b"extra", "Snd/changed.wav": b"new"},
            listed={**FILES, "Snd/changed.wav": b"old"})
    pin = ko_installs.manifest(base / "build/ko-reference/installer-1097", "installer-1097")
    tree = ko_character.Assets(base / INSTALL, manifest=pin)
    assert tree.get("snd/TURN.wav") == b"turn" and tree.has("UI/one.uif") and not tree.has("UI/two.uif")
    for name in ("Snd/extra.wav", "Snd/changed.wav"):
        try:
            tree.get(name)
            raise AssertionError("read %s, which the manifest does not list as it is" % name)
        except ValueError as error:
            assert "differs from its installer's (manifest" in str(error), str(error)
    assert list(tree.sources) == ["Snd/turn.wav"], tree.sources
    # A tree that is no install reads as before.
    assert ko_character.Assets(base / INSTALL).get("Snd/extra.wav") == b"extra"
print("PASS front-end inputs: an install's files read only as its manifest lists them")

# --- ko_front_end.Inputs and the turn sound's tree ------------------------------
with tempfile.TemporaryDirectory(prefix="n3e-front-end-inputs-") as td:
    base = pathlib.Path(td)
    for tree, files in (("a", {"UI/one.uif": b"a-one", "Data/sound.tbl.csv":
                               b'"1 - UInt32","2 - String","3 - Int32","4 - Int32"\n"7","Snd\\a.wav","0","3"\n'}),
                        ("b", {"UI/one.uif": b"b-one", "Data/sound.tbl": ko_tbl.encrypt(ko_tbl.build(
                            [6, 7, 5, 5], [[7, "Snd\\b.wav", 0, 40], [8, "Snd\\c.wav", 0, 2]]))})):
        for name, data in files.items():
            (base / tree / name).parent.mkdir(parents=True, exist_ok=True)
            (base / tree / name).write_bytes(data)
    a, b = ko_character.Assets(base / "a"), ko_character.Assets(base / "b")
    trees = ko_front_end.Inputs([a, b], [None, "b"])
    assert trees.get("UI/one.uif") == b"a-one" and trees.get("b:UI/one.uif") == b"b-one"
    assert trees.split("b:UI/one.uif") == (b, "UI/one.uif")
    assert trees.sources == {"UI/one.uif": hashlib.sha256(b"a-one").hexdigest(),
                             "b:UI/one.uif": hashlib.sha256(b"b-one").hexdigest()}, trees.sources
    for bad in ("c:UI/one.uif", 7):
        try:
            trees.get(bad)
            raise AssertionError("read %r" % (bad,))
        except ValueError:
            pass
    # The first tree's id stays an id (ko_audio's own table); another input's
    # is its own table's row, the CSV or the encrypted table, at most 16 at once.
    assert ko_front_end.sounds({"select": {"turn_sound": 7}}, trees, a) == {"front:select-turn": 7}
    assert ko_front_end.sounds({"select": {}}, trees, a) == {}
    turn = ko_front_end.sounds({"select": {"turn_sound": "b:7"}}, trees, a)["front:select-turn"]
    assert turn == dict(assets=b, path="Snd\\b.wav", maximum=16, input="b"), turn
    assert ko_front_end.sounds({"select": {"turn_sound": 7}}, ko_front_end.Inputs([b, a], [None, "a"]), a) == {
        "front:select-turn": dict(assets=b, path="Snd\\b.wav", maximum=16, input=None)}
    turn = ko_front_end.sounds({"select": {"turn_sound": "a:7"}}, ko_front_end.Inputs([b, a], [None, "a"]), b)
    assert turn == {"front:select-turn": dict(assets=a, path="Snd\\a.wav", maximum=3, input="a")}, turn
    for bad in (0, -1, "b:", "b:x", "b:9", "c:7", 7.0, True):
        try:
            ko_front_end.sounds({"select": {"turn_sound": bad}}, trees, a)
            raise AssertionError("took the turn sound %r" % (bad,))
        except ValueError:
            pass
    # Every KO path a recipe names is one recipe_paths lists (the prefix check's input).
    recipe = json.loads((MORADON / "front-end.json").read_text())
    listed = dict(ko_front_end.recipe_paths(recipe))
    assert listed["intro.character"] == "Intro/Intro.N3Chr" and "select.turn_sound" not in listed, listed
    assert ("select.turn_sound", "b:7") in ko_front_end.recipe_paths({"select": {"turn_sound": "b:7"}})
    assert {"screens.login.ui", "intro.lights[2]", "intro.backdrop.texture", "select.hall", "select.lights[1]",
            "select.character.joint", "select.character.animation", "select.character.plugs[0]",
            "music.tracks[1].path"} <= set(listed), sorted(listed)
print("PASS front-end inputs: paths read from their trees, the turn sound from its input's sound.tbl")

# --- ko_bake.package refuses before it writes (RQ-078 review) -------------------
import ko_bake  # noqa: E402

with tempfile.TemporaryDirectory(prefix="n3e-front-end-inputs-") as td:
    base = pathlib.Path(td)
    game = package(base, config={"front_end": "2145"})
    out = base / "out"
    out.mkdir()
    (out / "earlier").write_text("an earlier cook's output")
    saved, ko_bake.FRONT_END_GAME = ko_bake.FRONT_END_GAME, game
    try:
        ko_bake.package(str(ROOT / "games/demo"), {"gtd": "x.gtd", "opd": "x.opd", "assets": str(base)}, str(out),
                        features=True)
        raise AssertionError("package() took a front end the package does not offer")
    except choice.Refused as error:
        assert "front end '2145' is not one this package cooks" in str(error), str(error)
    finally:
        ko_bake.FRONT_END_GAME = saved
    assert sorted(p.name for p in out.iterdir()) == ["earlier"], list(out.iterdir())
print("PASS front-end choice: ko_bake.package refuses before it removes or writes anything")
