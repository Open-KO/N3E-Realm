"""Package item tooltip heads (PQ-354, D-194). Original n3e code.

Source form (package manifest key ``item_heads``)::

    {"self_token": "<selfname>",
     "items": [{"item": "demo:item/blade", "name_color": 16755021,
                "lines": [{"text": "(Reverse unique item)", "color": 16755021}]}]}

An item's tooltip starts with its inventory label (N3I1). With a head, the
client draws that first line in ``name_color`` (0xRRGGBB; yellow without a
head, as before) and the head's ``lines`` right under it, each centred like the
name, in their own colours; the rows after them are unchanged. When the package
names a ``self_token`` (optional), the client replaces each occurrence of it in
the first line with the viewer's own character name (client presentation only:
the server's item names stay as data). The rule is the 2233 client's tooltip
head (005aa8e0 and 004aad90, described with their addresses in
docs/implementation/evidence/pq-354-item-tooltip-head-2233.md); which colours,
lines and token a package uses is package data.

Cooked as ``item-heads.bin``: ``N3IH``, the token (u32 length and 0-32 bytes;
empty is none, otherwise printable ASCII 33-126), the head count (0-64; zero
only with a token), then per head the item id, the u32 name colour, the u32
line count (0-4) and each line's text (1-64 printable ASCII 32-126) and u32
colour. It needs engine 33, the presentation assets and the inventory, whose
defined items the heads must name, each once.
"""
import re
import struct

MAGIC = b"N3IH"
MAX_TOKEN, MAX_HEADS, MAX_LINES, MAX_TEXT = 32, 64, 4, 64
COLOR_MAX = 0xFFFFFF


def token_valid(token):
    return isinstance(token, str) and 1 <= len(token) <= MAX_TOKEN and all(33 <= ord(c) <= 126 for c in token)


def text_valid(text):
    return isinstance(text, str) and 1 <= len(text) <= MAX_TEXT and all(32 <= ord(c) <= 126 for c in text)


def color(value, what):
    if type(value) is not int or not 0 <= value <= COLOR_MAX:
        raise ValueError("item head %s colour" % what)
    return value


def cook(spec, game, inventory):
    """`spec` is the manifest's ``item_heads``; `inventory` its ``inventory``
    (whose item ids the heads must name)."""
    if not isinstance(spec, dict) or not set(spec) <= {"self_token", "items"} or "items" not in spec:
        raise ValueError("item heads fields")
    token = spec.get("self_token", "")
    if "self_token" in spec and not token_valid(token):
        raise ValueError("item heads token")
    items = spec["items"]
    if not isinstance(items, list) or len(items) > MAX_HEADS or (not items and not token):
        raise ValueError("item heads count")
    defined = {i["id"] for i in inventory["items"]}
    out = MAGIC + struct.pack("<I", len(token)) + token.encode("ascii") + struct.pack("<I", len(items))
    seen = set()
    for head in items:
        if not isinstance(head, dict) or set(head) != {"item", "name_color", "lines"}:
            raise ValueError("item head fields")
        item = head["item"]
        if not isinstance(item, str) or not re.fullmatch(re.escape(game) + r":[a-z][a-z0-9_/-]{0,95}", item):
            raise ValueError("item head namespace")
        if item not in defined or item in seen:
            raise ValueError("item head %s is not a defined inventory item, or is named twice" % item)
        seen.add(item)
        lines = head["lines"]
        if not isinstance(lines, list) or len(lines) > MAX_LINES:
            raise ValueError("item head line count")
        out += struct.pack("<I", len(item)) + item.encode("ascii")
        out += struct.pack("<II", color(head["name_color"], "name"), len(lines))
        for line in lines:
            if not isinstance(line, dict) or set(line) != {"text", "color"} or not text_valid(line["text"]):
                raise ValueError("item head line")
            out += struct.pack("<I", len(line["text"])) + line["text"].encode("ascii")
            out += struct.pack("<I", color(line["color"], "line"))
    return out


def parse(data, game, defined):
    """The heads of a cooked item-heads.bin as (token, {item: (name colour,
    [(text, colour)])}), refused as the readers refuse it."""
    at = [0]

    def take(n):
        if at[0] + n > len(data):
            raise ValueError("item heads truncated")
        at[0] += n
        return data[at[0] - n:at[0]]

    def number():
        return struct.unpack("<I", take(4))[0]

    def text(limit):
        n = number()
        if n > limit:
            raise ValueError("item heads string bound")
        return take(n).decode("ascii")
    if take(4) != MAGIC:
        raise ValueError("item heads magic")
    token = text(MAX_TOKEN)
    if token and not token_valid(token):
        raise ValueError("item heads token")
    count = number()
    if count > MAX_HEADS or (not count and not token):
        raise ValueError("item heads count")
    heads = {}
    for _ in range(count):
        item = text(128)
        if not item.startswith(game + ":") or item not in defined or item in heads:
            raise ValueError("item head item")
        name, n = number(), number()
        if name > COLOR_MAX or n > MAX_LINES:
            raise ValueError("item head bounds")
        lines = []
        for _ in range(n):
            t = text(MAX_TEXT)
            c = number()
            if not text_valid(t) or c > COLOR_MAX:
                raise ValueError("item head line")
            lines.append((t, c))
        heads[item] = (name, lines)
    if at[0] != len(data):
        raise ValueError("item heads trailing bytes")
    return token, heads
