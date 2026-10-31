"""PQ-354 (D-194): the package item tooltip heads (item-heads.bin, N3IH).

The cooker (tools/assetc/item_heads.py) writes the token, the heads and their
lines in order, and refuses unknown fields, a token, item, colour or line out
of bounds, an item the inventory does not define or names twice, nothing to
draw, and a package below engine 33 (the cooker also refuses one without the
presentation assets or an inventory); its parser refuses malformed files as the
readers do. Both readers
(the client's asset check and the server's content check) run on a cooked
release, with hostile files, in tests/item_heads_live.py; the server's reader
has its own unit tests (cargo test item_heads) and the client's tooltip rule
is checked by build/client/n3e-hud-check.
"""
import json
import shutil
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/assetc"))
import item_heads  # noqa: E402
import main  # noqa: E402

INVENTORY = {"items": [{"id": "demo:item/blade"}, {"id": "demo:item/potion"}]}
KIND = {"text": "(Reverse unique item)", "color": 0xFFAD4D}
GOOD = {"self_token": "<selfname>", "items": [{"item": "demo:item/blade", "name_color": 0xFFAD4D, "lines": [KIND]}]}


def u(*xs):
    return b"".join(struct.pack("<I", x) for x in xs)


def s(text):
    return u(len(text)) + text.encode()


def refused(spec, why, inventory=INVENTORY):
    try:
        item_heads.cook(spec, "demo", inventory)
    except ValueError:
        return
    raise AssertionError("cooker accepted " + why)


cooked = item_heads.cook(GOOD, "demo", INVENTORY)
expected = b"N3IH" + s("<selfname>") + u(1) + s("demo:item/blade") + u(0xFFAD4D, 1) + s(KIND["text"]) + u(0xFFAD4D)
assert cooked == expected, cooked
assert item_heads.parse(cooked, "demo", {"demo:item/blade"}) == (
    "<selfname>", {"demo:item/blade": (0xFFAD4D, [(KIND["text"], 0xFFAD4D)])})
# A token alone (labels only), heads alone (no token), the bounds' edges.
assert item_heads.cook({"self_token": "<x>", "items": []}, "demo", INVENTORY) == b"N3IH" + s("<x>") + u(0)
assert item_heads.cook({"items": [{"item": "demo:item/potion", "name_color": 0, "lines": []}]}, "demo",
                       INVENTORY) == b"N3IH" + u(0, 1) + s("demo:item/potion") + u(0, 0)
edge = {"self_token": "~" * 32, "items": [{"item": "demo:item/blade", "name_color": 0xFFFFFF,
                                          "lines": [{"text": " " * 64, "color": 0xFFFFFF}] * 4}]}
assert item_heads.parse(item_heads.cook(edge, "demo", INVENTORY), "demo", {"demo:item/blade"})[0] == "~" * 32
head = GOOD["items"][0]
refused({**GOOD, "extra": 1}, "an unknown field")
refused({"self_token": "<selfname>"}, "no items list")
refused({"items": []}, "nothing to draw")
refused({**GOOD, "self_token": ""}, "an empty token")
refused({**GOOD, "self_token": "~" * 33}, "a 33-byte token")
refused({**GOOD, "self_token": "<self name>"}, "a token with a space")
refused({**GOOD, "self_token": 7}, "a token that is not a string")
refused({**GOOD, "items": [dict(head, item="demo:item/sword")]}, "an undefined item")
refused({**GOOD, "items": [dict(head, item="other:item/blade")]}, "another game's item")
refused({**GOOD, "items": [head, head]}, "an item named twice")
refused({**GOOD, "items": [head] * 65}, "65 heads")
refused({**GOOD, "items": [dict(head, name_color=0x1000000)]}, "a name colour above 0xffffff")
refused({**GOOD, "items": [dict(head, name_color=-1)]}, "a negative name colour")
refused({**GOOD, "items": [dict(head, name_color=True)]}, "a boolean name colour")
refused({**GOOD, "items": [dict(head, lines=[KIND] * 5)]}, "five lines")
refused({**GOOD, "items": [dict(head, lines=[dict(KIND, text="")])]}, "an empty line")
refused({**GOOD, "items": [dict(head, lines=[dict(KIND, text="x" * 65)])]}, "a 65-byte line")
refused({**GOOD, "items": [dict(head, lines=[dict(KIND, text="tab\there")])]}, "a control byte")
refused({**GOOD, "items": [dict(head, lines=[dict(KIND, text="café")])]}, "a non-ASCII line")
refused({**GOOD, "items": [dict(head, lines=[dict(KIND, color=0x1000000)])]}, "a line colour above 0xffffff")
refused({**GOOD, "items": [dict(head, lines=[dict(KIND, extra=1)])]}, "an unknown line field")
refused({**GOOD, "items": [{"item": "demo:item/blade", "name_color": 1}]}, "a head without lines")

bad = {
    "magic": b"N3IJ" + cooked[4:],
    "truncated": cooked[:-1],
    "trailing": cooked + b"\0",
    "nothing": b"N3IH" + u(0, 0),
    "long token": b"N3IH" + s("~" * 33) + u(0),
    "token space": b"N3IH" + s("a b") + u(0),
    "65 heads": b"N3IH" + s("<x>") + u(65),
    "undefined item": b"N3IH" + u(0, 1) + s("demo:item/sword") + u(0, 0),
    "twice": b"N3IH" + u(0, 2) + (s("demo:item/blade") + u(0, 0)) * 2,
    "name colour": b"N3IH" + u(0, 1) + s("demo:item/blade") + u(0x1000000, 0),
    "five lines": b"N3IH" + u(0, 1) + s("demo:item/blade") + u(0, 5) + (s("x") + u(0)) * 5,
    "empty line": b"N3IH" + u(0, 1) + s("demo:item/blade") + u(0, 1) + s("") + u(0),
    "line colour": b"N3IH" + u(0, 1) + s("demo:item/blade") + u(0, 1) + s("x") + u(0x1000000),
}
for name, data in bad.items():
    try:
        item_heads.parse(data, "demo", {"demo:item/blade"})
    except ValueError:
        continue
    raise AssertionError("parse accepted " + name)

# The cook refuses the key below engine 33 (the demo package is engine 11, and
# has no inventory either).
with tempfile.TemporaryDirectory(dir=ROOT / "build") as tmp:
    tmp = Path(tmp)
    source = tmp / "demo"
    shutil.copytree(ROOT / "games/demo", source)
    manifest = json.loads((source / "package.json").read_text())
    assert manifest["engine_version"] < 33 and "inventory" not in manifest
    (source / "package.json").write_text(json.dumps({**manifest, "item_heads": GOOD}))
    try:
        main.cook(source, tmp / "out")
    except ValueError as e:
        assert str(e) == "item heads compatibility", e
    else:
        raise AssertionError("cooked item heads below engine 33")
print(f"PASS item heads: N3IH cooked in order ({len(cooked)} bytes); the cooker refuses 22 bad sources and engine < 33; "
      f"the parser refuses {len(bad)} malformed files")
