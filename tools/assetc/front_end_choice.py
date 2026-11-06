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

A choice may read more than one tree (RQ-084): every input after the first
has a `name`, and a recipe path `<name>:<path>` reads from that input, any
other from the first. A tree that is a reference install
(`build/ko-reference/<name>/client`) must be a pinned one (`ko_installs`), and
its manifest must name the pinned installer, before any cook reads it.
"""
import json
import pathlib
import re

import ko_installs

CONFIG = "realm-config.json"
CATALOGUE = "front-ends.json"
# The realm-config.json keys this cook knows; any other is refused (a typo
# would otherwise cook the default without a word). RQ-002: `create`, the
# character-create choices (tools/assetc/ko_create.py). RQ-203: `world_dust`,
# whether the world draws worn items' dust overlays (world_dust below).
CONFIG_KEYS = {"front_end", "create", "world_dust"}
# RQ-203 (Q120): `world_dust`'s values. KO's world puts a dust texture on a worn
# hand plug or armour part by its durability (1298 0045d5f0, 1097 004535a0);
# `draw` cooks it into effects.bin (N3E6), `none` (the default) leaves the
# world as before.
WORLD_DUST = ("none", "draw")
ENTRY_KEYS = {"recipe", "inputs"}
INPUT_KEYS = {"tree", "get"}
# RQ-084: the name a recipe path's prefix gives the input (required after the first).
INPUT_OPTIONAL = {"name"}
# A recipe path's tree prefix: `<input name>:<path>`. No KO path holds a
# colon (ko_character.Assets refuses one), so the first colon is the prefix's.
PREFIX = ":"
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
        names = set()
        for at, item in enumerate(inputs):
            if (type(item) is not dict or not INPUT_KEYS <= set(item) <= INPUT_KEYS | INPUT_OPTIONAL
                    or tree_path(item["tree"]) is None
                    or type(item["get"]) is not str or not 0 < len(item["get"]) <= MAX_HINT):
                raise Refused("%s: %s's inputs are each a repository-relative tree and how to get it" % (path, client))
            name = item.get("name")
            if name is None and at > 0:
                raise Refused("%s: %s's input %s needs a name: a recipe path names it as <name>:<path>"
                              % (path, client, item["tree"]))
            if name is not None:
                if type(name) is not str or not CLIENT_ID.match(name):
                    raise Refused("%s: %s's input name %r is not lower-case letters, digits and -, up to 32"
                                  % (path, client, name))
                if name in names:
                    raise Refused("%s: %s names two inputs %s" % (path, client, name))
                names.add(name)
            try:
                ko_installs.install_of(item["tree"])
            except ValueError as error:
                raise Refused("%s: %s's input %s" % (path, client, error))
    return offered


def choose(game, root="."):
    """The front end the realm owner chose (`realm-config.json`), checked
    against the package and the inputs on this machine: `resolve`'s result,
    with `create`, the character-create choice (`ko_create.plan`, RQ-002; None
    for a package without create rules). `root` is the checkout the input
    trees are relative to."""
    game = pathlib.Path(game)
    path = game / CONFIG
    config = read(path, "the realm's choices; content/front-end.md, \"Choosing the client\"")
    unknown = sorted(set(config) - CONFIG_KEYS)
    if unknown:
        raise Refused("%s: unknown key %s (it knows %s)" % (path, ", ".join(unknown), ", ".join(sorted(CONFIG_KEYS))))
    dust_choice(config, path)
    offered = catalogue(game)
    client = config.get("front_end")
    if type(client) is not str:
        raise Refused("%s: front_end must name a KO client, one of %s" % (path, ", ".join(sorted(offered))))
    if client not in offered:
        raise Refused("%s: front end %r is not one this package cooks; it cooks %s (%s)"
                      % (path, client, ", ".join(sorted(offered)), game / CATALOGUE))
    # RQ-002: the create rules' choice, checked before any input is read; None
    # for a package without create rules.
    import ko_create
    chosen = ko_create.plan(game, client, config.get("create", {}))
    return dict(resolve(game, client, root, offered), create=chosen)


def dust_choice(config, path):
    """`world_dust` of a read realm-config.json, checked: True for `draw`."""
    value = config.get("world_dust", "none")
    if type(value) is not str or value not in WORLD_DUST:
        raise Refused("%s: world_dust must be one of %s, not %r" % (path, ", ".join(WORLD_DUST), value))
    return value == "draw"


def world_dust(game):
    """Whether the realm owner chose the world's dust overlay (RQ-203):
    realm-config.json's `world_dust` is `draw` (default `none`)."""
    path = pathlib.Path(game) / CONFIG
    return dust_choice(read(path, "the realm's choices; content/appearance.md, \"Durability dust\""), path)


def split(path):
    """(input name or None, path) of a recipe path: `<name>:<path>` names an
    input, any other path the first."""
    name, sep, rest = path.partition(PREFIX)
    return (name, rest) if sep else (None, path)


def resolve(game, client, root=".", offered=None):
    """One offered front end with its inputs on this machine: {client,
    recipe, inputs, names, pins}: the input trees in front-ends.json's order
    (the first is the tree an unprefixed recipe path names), each one's name
    (None for an unnamed first) and, for a reference install, its checked
    manifest (`ko_installs.manifest`; None for any other tree). Every tree
    prefix the recipe's paths use must name one of the inputs."""
    game, root = pathlib.Path(game), pathlib.Path(root)
    offered = catalogue(game) if offered is None else offered
    if client not in offered:
        raise Refused("front end %r is not one %s offers" % (client, game / CATALOGUE))
    inputs, names, pins = [], [], []
    for item in offered[client]["inputs"]:
        tree = root / tree_path(item["tree"])
        if not tree.is_dir():
            raise Refused("front end %r needs %s, which is missing on this machine: %s"
                          % (client, item["tree"], item["get"]))
        install = ko_installs.install_of(item["tree"])
        pin = None
        if install is not None:
            try:
                pin = ko_installs.manifest(tree.parent, install)
            except ValueError as error:
                raise Refused("front end %r reads %s: %s" % (client, item["tree"], error))
        inputs.append(tree)
        names.append(item.get("name"))
        pins.append(pin)
    recipe = game / offered[client]["recipe"]
    import ko_front_end  # the recipe's fields are the cook's
    known = [n for n in names if n is not None]
    for where, path in ko_front_end.recipe_paths(read(recipe, "front end %r's recipe" % client)):
        name, _ = split(path)
        if name is not None and name not in known:
            raise Refused("%s: %s names input %r, which front end %r does not have (%s)"
                          % (recipe, where, name, client,
                             "its inputs: " + ", ".join(known) if known else "its one input has no name"))
    return dict(client=client, recipe=recipe, inputs=inputs, names=names, pins=pins)
