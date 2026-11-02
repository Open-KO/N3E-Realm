"""The realm's front-end client choice (spec 11 "The client choice", RQ-078).

A package lists, in `front-ends.json`, the KO clients its front end can look
and behave like: each a recipe for `ko_front_end` (the files, bindings and
placements of that client's screens) and the input trees the recipe reads.
The realm owner names one in the package's `realm-config.json` (`front_end`).
`choose` checks both and refuses, before any cooking, a choice the package
does not offer or whose inputs are missing, each with a message that names
the file to change or the input to get. The engine plays whatever the cooked
`front-end.bin` says; this module knows no client: ids, recipes and trees are
the package's data (content/front-end.md, "Choosing the client").
"""
import json
import pathlib
import re

CONFIG = "realm-config.json"
CATALOGUE = "front-ends.json"
# The realm-config.json keys this cook knows; any other is refused (a typo
# would otherwise cook the default without a word).
CONFIG_KEYS = {"front_end"}
ENTRY_KEYS = {"recipe", "inputs"}
INPUT_KEYS = {"tree", "get"}
CLIENT_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,31}\Z")
RECIPE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\.json\Z")
MAX_INPUTS = 4
MAX_HINT = 200
MAX_FILE = 1 << 20


class Refused(ValueError):
    """A front-end choice the cook will not make, with the reason a realm owner reads."""


def read(path, what):
    path = pathlib.Path(path)
    if not path.is_file():
        raise Refused("%s: missing (%s)" % (path, what))
    if path.stat().st_size > MAX_FILE:
        raise Refused("%s: over %d bytes" % (path, MAX_FILE))
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise Refused("%s: not JSON (%s)" % (path, error))
    if type(value) is not dict:
        raise Refused("%s: not a JSON object" % path)
    return value


def tree_path(tree):
    """A repository-relative input tree, never absolute or leaving the checkout."""
    if type(tree) is not str or not tree or "\\" in tree:
        return None
    path = pathlib.PurePosixPath(tree)
    if path.is_absolute() or any(part in ("", ".", "..") for part in tree.split("/")):
        return None
    return path


def catalogue(game):
    """The package's front ends, by client id, checked whole: {id: entry}."""
    game = pathlib.Path(game)
    path = game / CATALOGUE
    offered = read(path, "the front ends this package cooks")
    if not offered:
        raise Refused("%s: offers no front end" % path)
    for client, entry in offered.items():
        if not CLIENT_ID.match(client):
            raise Refused("%s: %r is not a client id (lower-case letters, digits and -, up to 32)" % (path, client))
        if type(entry) is not dict or set(entry) != ENTRY_KEYS:
            raise Refused("%s: %s needs exactly %s" % (path, client, ", ".join(sorted(ENTRY_KEYS))))
        recipe = entry["recipe"]
        if type(recipe) is not str or not RECIPE.match(recipe):
            raise Refused("%s: %s's recipe must be a .json file beside it" % (path, client))
        if not (game / recipe).is_file():
            raise Refused("%s: %s's recipe %s is missing" % (path, client, game / recipe))
        inputs = entry["inputs"]
        if type(inputs) is not list or not 1 <= len(inputs) <= MAX_INPUTS:
            raise Refused("%s: %s needs 1 to %d inputs" % (path, client, MAX_INPUTS))
        for item in inputs:
            if (type(item) is not dict or set(item) != INPUT_KEYS or tree_path(item["tree"]) is None
                    or type(item["get"]) is not str or not 0 < len(item["get"]) <= MAX_HINT):
                raise Refused("%s: %s's inputs are each a repository-relative tree and how to get it" % (path, client))
    return offered


def choose(game, root="."):
    """The front end the realm owner chose (`realm-config.json`), checked
    against the package and the inputs on this machine: `resolve`'s result.
    `root` is the checkout the input trees are relative to."""
    game = pathlib.Path(game)
    path = game / CONFIG
    config = read(path, "the realm's choices; content/front-end.md, \"Choosing the client\"")
    unknown = sorted(set(config) - CONFIG_KEYS)
    if unknown:
        raise Refused("%s: unknown key %s (it knows %s)" % (path, ", ".join(unknown), ", ".join(sorted(CONFIG_KEYS))))
    offered = catalogue(game)
    client = config.get("front_end")
    if type(client) is not str:
        raise Refused("%s: front_end must name a KO client, one of %s" % (path, ", ".join(sorted(offered))))
    if client not in offered:
        raise Refused("%s: front end %r is not one this package cooks; it cooks %s (%s)"
                      % (path, client, ", ".join(sorted(offered)), game / CATALOGUE))
    return resolve(game, client, root, offered)


def resolve(game, client, root=".", offered=None):
    """One offered front end with its inputs on this machine: {client,
    recipe, inputs}, the input trees in the recipe's order (the first is the
    tree its paths name)."""
    game, root = pathlib.Path(game), pathlib.Path(root)
    offered = catalogue(game) if offered is None else offered
    if client not in offered:
        raise Refused("front end %r is not one %s offers" % (client, game / CATALOGUE))
    inputs = []
    for item in offered[client]["inputs"]:
        tree = root / tree_path(item["tree"])
        if not tree.is_dir():
            raise Refused("front end %r needs %s, which is missing on this machine: %s"
                          % (client, item["tree"], item["get"]))
        inputs.append(tree)
    return dict(client=client, recipe=game / offered[client]["recipe"], inputs=inputs)
