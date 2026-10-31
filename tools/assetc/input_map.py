"""Package input map (PQ-009, D-136): engine actions bound to physical keys.

Source form (package manifest key ``input``)::

    {"bindings": [{"action": "run_toggle", "keys": ["T"]},
                  {"action": "hotbar_page_1", "keys": ["F1"], "forbid": ["Alt"], "typing": true}]}

``require``/``forbid`` name modifiers that must be down/up; ``typing`` lets the
binding fire while a text field has focus. One key may bind several press
actions: the client tries them in table order. ``MouseLeft`` (a left press in
the world) and ``MouseLeftDouble`` (the left release that completes a double
click) are mouse gestures (PQ-011): they bind press actions only, without the
typing flag. Cooked as ``input.bin``
(``N3I1``). The vocabularies match ``client/assets/input_names.h``
(``tests/input_map.py`` checks that).

An optional ``names`` object sets the name display that ``names_toggle`` flips
(PQ-014): ``{"shown": true, "hides": ["self", "players"]}``. ``shown`` is the
state at start (KO: on, the static byte ``006d42e4`` = 1); ``hides`` lists the
actor classes the toggle hides (KO: the local player and other players, whose
name callbacks ``0046b5a0``/``0046ea90`` read the flag; NPC names, drawn by
``00459820``, ignore it). A table with ``names`` cooks as ``N3I2``: the ``N3I1``
rows and one u32 (bit 0 shown, bits 1-3 self/players/npcs). Without it the
client shows every name and the toggle hides every class.

``names`` may also carry ``lifetime`` (PQ-169), the range at which other
players' names exist: ``{"from": "self", "acquire": 10, "release": 20,
"exempt": ["party"]}``. A remote player's name is made once it is closer than
``acquire`` metres to the measuring point (``self``: the local player's
displayed position; ``camera``: the camera eye) and dropped once it is farther
than ``release``; in between it stays as it was. ``exempt`` classes keep their
name at any range (``party``: members of the local player's party). KO: the
player-manager tick ``00470900`` builds the label below 10.0 (``006a425c``) and
frees it above 20.0 (``006a4260``), measured from the local player's position
(``[00818794]+0x98``), and exempts party members (``+0x7dc``). A table with a
lifetime cooks as ``N3I3``: the ``N3I2`` layout followed by u32 from, f32
acquire, f32 release and u32 exempt (bit 0 party). Without it every other
player's name exists at any range.

``names`` may also carry ``party`` (PQ-166), how the names of other players in
the local player's party differ: ``{"while_hidden": true, "beyond_distance":
true, "color": 16776960}``. ``while_hidden`` keeps them drawn while the toggle
hides other players; ``beyond_distance`` lifts the nameplate style's camera
``distance`` limit for them; ``color`` (optional, 0xRRGGBB) replaces the other-
player colour, taken when the label is refreshed (with a lifetime: every frame
for an exempt class or inside ``acquire``; see ``content/nameplates.md``). KO:
the party window tick ``0051c5b0`` sets other-player ``+0x7dc`` on each member
in view; the name callback ``0046ea90`` then draws while O hides names and skips
the 48 m limit unless the zone's Zones.tbl column 23 is 0, and the label refresh
``0046e840`` colours the name ``0xffffff00``. The KO bake sets
``beyond_distance`` from that column of the package's zone row. A table with
``party`` cooks as ``N3I4``: the ``N3I2`` layout, u32 1 and the lifetime record
or u32 0 without one, then u32 flags (bit 0 while_hidden, bit 1
beyond_distance, bit 2 color set) and u32 color (0 when unset). Tables without
``party`` keep N3I1-N3I3.

``names`` may also carry ``distance`` (PQ-173), a camera distance limit per
name class that replaces the nameplate style's ``distance`` for that class:
``{"players": 33}``. A name is drawn only while the camera is closer than the
limit (party members with ``beyond_distance`` still skip it). KO: the other-
player name callback ``0046ea90`` uses 33.0 (``006a4250``) instead of 48.0
(``006a40dc``) when the zone key (``0046c9d0``) is ``0x140`` (Zones.tbl key
320); the self (``0046b5a0``) and NPC (``00459820``) callbacks always use 48.0.
The KO bake sets it from the package's zone key (``games/moradon/nameplates.json``
``zone_distance``). A table with ``distance`` cooks as ``N3I5``: the ``N3I2``
layout, u32 0/1 and the lifetime record, u32 0/1 and the party record, then u32
class mask (bits 0-2 self/players/npcs, at least one) and one f32 per set bit
in class order (finite, 0 < limit <= 1000). Tables without ``distance`` keep
N3I1-N3I4.

``names`` may also carry ``npc_lifetime`` (PQ-174), the range at which NPC
names exist: ``{"from": "self", "acquire": 10, "release": 20, "rule": "band",
"always": false, "drop_dead": true}``. An NPC's name is made once it is closer
than ``acquire`` metres to the measuring point (as ``lifetime``); none exists
when the NPC enters view. ``rule`` ``band`` drops it only while it is at least
``acquire`` but closer than ``release`` and leaves it at ``release`` or
farther; ``beyond`` drops it once it is farther than ``release`` (the
``lifetime`` rule). ``always`` keeps every NPC's name at any range and lifts the
camera ``distance`` limit for NPCs. ``drop_dead`` drops a dead NPC's name once
its death clip has played. KO: the manager tick ``00470900`` builds an NPC's
name font below 10.0 (``006a425c``) of the local player's position, frees it
while 10.0 <= d < 20.0 (``006a4260``, ``00470be0``) and keeps it at 20.0 or
farther; NPCs whose ``NPC_Looks.tbl`` column 36 is 1 are refreshed every tick
(``00470baa``) and skip the 48 m camera limit (``00459856``); a dead NPC (state
5, entered when its dying clip ends, ``00457e57``) moves to the corpse map,
whose loop frees its font (``00470c67``). The KO bake sets ``always`` from the
looks row of the package's NPC template (``ko_bake.npc_names``). A table with
``npc_lifetime`` cooks as ``N3I6``: the ``N3I5`` layout, whose class mask may
be 0 (no limits), then u32 from, f32 acquire, f32 release and u32 flags (bit 0
band, bit 1 always, bit 2 drop_dead). Tables without ``npc_lifetime`` keep
N3I1-N3I5.

``names`` may also carry ``npc_info`` (PQ-177), the operator info line drawn
above an NPC's name: ``{"color": 65280, "text": "ID({id}) : TYPE({state:0})"}``. The
client replaces the one ``{id}`` with the NPC's entity id and draws the line
in ``color`` (0xRRGGBB) above the name, only while the capability set the
server projects holds ``server.inspect``; the table styles the line and cannot
enable it. KO: the NPC label refresh ``00465070`` formats ``ID(%d) :
TYPE(%d)`` (``006d44f0``) with the wire ID and NPC byte ``+0x7c0`` in
``0xff00ff00`` when the local MyInfo authority byte (``+0x4a4``) is 0, and the
NPC name callback ``00459820`` draws it 5 px above the name. ``TYPE`` is 0
until opcode ``0x5d`` sets the byte (PQ-186: the state the AI server reports
for an NPC an operator traced). The text may carry one state placeholder (PQ-186),
which the client replaces with the last server AI state reported for an NPC
an operator traced (``World.traces``, sent only to sessions the server leases
``server.inspect``); ``{state:FALLBACK}`` shows FALLBACK (1-16 printable ASCII
bytes, no brace) while none was reported, ``{state}`` nothing (the KO table
writes ``{state:0}``, KO's initial byte). ``text`` is 1-64 printable ASCII bytes
with exactly one ``{id}``, at most one state placeholder and no other brace. A table with ``npc_info`` cooks
as ``N3I7``: the ``N3I5`` layout, whose class mask may be 0, u32 0/1 and the
``N3I6`` NPC lifetime record when 1, then u32 color and the text as a string.
Tables without ``npc_info`` keep N3I1-N3I6.

``names`` may also carry ``operator_chat`` (PQ-178), the style of a chat line
the server marks as an operator's (``Chat.from_operator``): ``{"color":
13474815}``. The client draws a marked line in ``color`` (0xRRGGBB) instead of
the chat text's own colour; without ``operator_chat`` a marked line looks like
any other. The table styles the line and cannot mark one. KO: the chat handler
``005cac80`` sets ``0xffcd9bff`` (``005cb2f5``) for any type but 7 when the
sender found in the other-player map has authority 0, or the line is the local
player's own and its authority is 0, and passes it to the chat window
(``00543410``) and the balloon (``00456d90``). A table with ``operator_chat``
cooks as ``N3I8``: the ``N3I7`` layout with a u32 0/1 before the NPC info line
(present when 1), then the u32 colour. Tables without ``operator_chat`` keep
N3I1-N3I7.
"""
import math

from common import f, string, u

ACTIONS = (
    [f"hotbar_use_{i}" for i in range(1, 9)]
    + [f"hotbar_page_{i}" for i in range(1, 9)]
    + ["hotbar_page_prev", "hotbar_page_next",
       "move_forward", "move_backward", "turn_left", "turn_right", "turbo",
       "camera_pitch_up", "camera_pitch_down",
       "auto_move", "run_toggle", "attack_toggle",
       "target_enemy", "target_party", "target_npc", "target_cycle",
       "rest_toggle", "inventory", "character", "skills", "minimap", "help", "chat", "respawn",
       "loot_nearest", "window_page_prev", "window_page_next",
       "command_list", "names_toggle", "camera_mode", "hide_hud", "chat_size", "message_size",
       "screenshot", "cancel", "attack_pick", "attack_target"]
)
HELD = {"move_forward", "move_backward", "turn_left", "turn_right", "turbo",
        "camera_pitch_up", "camera_pitch_down"}
KEYS = (
    [chr(c) for c in range(ord("A"), ord("Z") + 1)]
    + [str(i) for i in range(1, 10)] + ["0"]
    + [f"F{i}" for i in range(1, 13)]
    + ["Up", "Down", "Left", "Right", "PageUp", "PageDown", "Home", "End", "Insert", "Delete",
       "Return", "KeypadEnter", "KeypadMinus", "KeypadPlus", "Space", "Tab",
       "LeftBracket", "RightBracket", "Minus", "Equals", "Comma", "Period", "Slash",
       "Semicolon", "Apostrophe", "Backslash", "Grave", "Escape",
       "MouseLeft", "MouseLeftDouble"]
)
MOUSE = ("MouseLeft", "MouseLeftDouble")
# Engine-reserved: reconnect, tools editor, tools terminal (D-136).
RESERVED = ("F12", "F11", "Grave")
MODIFIERS = ("Shift", "LeftShift", "Ctrl", "Alt")
MAX_BINDINGS = 128
NAME_CLASSES = ("self", "players", "npcs")
LIFETIME_FROM = ("self", "camera")
LIFETIME_EXEMPT = ("party",)
NPC_LIFETIME_RULES = ("beyond", "band")
NPC_LIFETIME_FIELDS = {"from", "acquire", "release", "rule", "always", "drop_dead"}
NPC_INFO_FIELDS = {"color", "text"}
OPERATOR_CHAT_FIELDS = {"color"}
MAX_NPC_INFO = 64
PARTY_FIELDS = ("while_hidden", "beyond_distance")
MAX_LIFETIME = 1000
MAX_NAME_DISTANCE = 1000
MAX_KEYS = 4


def _mask(names, what):
    if not isinstance(names, list) or len(set(names)) != len(names) or any(n not in MODIFIERS for n in names):
        raise ValueError(f"input {what} modifiers")
    return sum(1 << MODIFIERS.index(n) for n in names)


def flatten(policy):
    """The ordered (action, key, require, forbid, flags) rows a policy cooks to."""
    if not isinstance(policy, dict) or not {"bindings"} <= set(policy) <= {"bindings", "names"} \
            or not isinstance(policy["bindings"], list):
        raise ValueError("input map vocabulary")
    rows, seen = [], set()
    for b in policy["bindings"]:
        if not isinstance(b, dict) or not {"action", "keys"} <= set(b) <= {"action", "keys", "require", "forbid", "typing"}:
            raise ValueError("input binding vocabulary")
        action, keys = b["action"], b["keys"]
        if action not in ACTIONS:
            raise ValueError(f"input action {action!r}")
        if not isinstance(keys, list) or not 1 <= len(keys) <= MAX_KEYS or len(set(keys)) != len(keys):
            raise ValueError("input keys")
        require, forbid = _mask(b.get("require", []), "required"), _mask(b.get("forbid", []), "forbidden")
        if require & forbid:
            raise ValueError("input modifier both required and forbidden")
        typing = b.get("typing", False)
        if type(typing) is not bool:
            raise ValueError("input typing flag")
        for key in keys:
            if not isinstance(key, str) or key not in KEYS:
                raise ValueError(f"input key {key!r}")
            if key in RESERVED:
                raise ValueError(f"input key {key} is engine-reserved")
            if key in MOUSE and (action in HELD or typing):
                raise ValueError(f"input {key} binds press actions only, without typing")
            if (action, key, require, forbid) in seen:
                raise ValueError("duplicate input binding")
            seen.add((action, key, require, forbid))
            rows.append((action, key, require, forbid, int(typing)))
    if not 1 <= len(rows) <= MAX_BINDINGS:
        raise ValueError("input binding count")
    return rows


def names(policy):
    """The cooked name-display word, or None when the table has no ``names``."""
    if "names" not in policy:
        return None
    n = policy["names"]
    if not isinstance(n, dict) or not {"shown", "hides"} <= set(n) <= {"shown", "hides", "lifetime", "party", "distance",
                                                                     "npc_lifetime", "npc_info",
                                                                     "operator_chat"} \
            or type(n["shown"]) is not bool:
        raise ValueError("input names vocabulary")
    hides = n["hides"]
    if not isinstance(hides, list) or not hides or len(set(hides)) != len(hides) \
            or any(c not in NAME_CLASSES for c in hides):
        raise ValueError("input names classes")
    return int(n["shown"]) | sum(2 << NAME_CLASSES.index(c) for c in hides)


def lifetime(policy):
    """The cooked other-player label lifetime record, or None without one."""
    names(policy)
    if "lifetime" not in policy.get("names", {}):
        return None
    life = policy["names"]["lifetime"]
    if not isinstance(life, dict) or set(life) != {"from", "acquire", "release", "exempt"}:
        raise ValueError("input names lifetime vocabulary")
    if life["from"] not in LIFETIME_FROM:
        raise ValueError("input names lifetime measuring point")
    acquire, release = life["acquire"], life["release"]
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in (acquire, release)) \
            or not 0 < acquire <= release <= MAX_LIFETIME:
        raise ValueError("input names lifetime radii")
    exempt = life["exempt"]
    if not isinstance(exempt, list) or len(set(exempt)) != len(exempt) \
            or any(c not in LIFETIME_EXEMPT for c in exempt):
        raise ValueError("input names lifetime exempt classes")
    return (u(LIFETIME_FROM.index(life["from"])) + f([acquire, release])
            + u(sum(1 << LIFETIME_EXEMPT.index(c) for c in exempt)))


def party(policy):
    """The cooked party-name record (flags, colour), or None without one."""
    names(policy)
    if "party" not in policy.get("names", {}):
        return None
    p = policy["names"]["party"]
    if not isinstance(p, dict) or not set(PARTY_FIELDS) <= set(p) <= {*PARTY_FIELDS, "color"} \
            or any(type(p[k]) is not bool for k in PARTY_FIELDS):
        raise ValueError("input names party vocabulary")
    color = p.get("color")
    if "color" in p and (type(color) is not int or not 0 <= color <= 0xFFFFFF):
        raise ValueError("input names party colour")
    flags = int(p["while_hidden"]) | int(p["beyond_distance"]) << 1 | int("color" in p) << 2
    return u(flags) + u(color or 0)


def distance(policy):
    """The cooked per-class camera distance record (mask, limits), or None without one."""
    names(policy)
    if "distance" not in policy.get("names", {}):
        return None
    d = policy["names"]["distance"]
    if not isinstance(d, dict) or not d or any(c not in NAME_CLASSES for c in d):
        raise ValueError("input names distance classes")
    if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 < v <= MAX_NAME_DISTANCE
           for v in d.values()):
        raise ValueError("input names distance limit")
    order = [c for c in NAME_CLASSES if c in d]
    return u(sum(1 << NAME_CLASSES.index(c) for c in order)) + f([d[c] for c in order])


def npc_lifetime(policy):
    """The cooked NPC label lifetime record, or None without one."""
    names(policy)
    if "npc_lifetime" not in policy.get("names", {}):
        return None
    life = policy["names"]["npc_lifetime"]
    if not isinstance(life, dict) or set(life) != NPC_LIFETIME_FIELDS:
        raise ValueError("input names npc_lifetime vocabulary")
    if life["from"] not in LIFETIME_FROM:
        raise ValueError("input names npc_lifetime measuring point")
    acquire, release = life["acquire"], life["release"]
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in (acquire, release)) \
            or not 0 < acquire <= release <= MAX_LIFETIME:
        raise ValueError("input names npc_lifetime radii")
    if life["rule"] not in NPC_LIFETIME_RULES:
        raise ValueError("input names npc_lifetime rule")
    if any(type(life[k]) is not bool for k in ("always", "drop_dead")):
        raise ValueError("input names npc_lifetime flags")
    flags = NPC_LIFETIME_RULES.index(life["rule"]) | int(life["always"]) << 1 | int(life["drop_dead"]) << 2
    return u(LIFETIME_FROM.index(life["from"])) + f([acquire, release]) + u(flags)


def npc_info(policy):
    """The cooked NPC info line record (colour, text), or None without one."""
    names(policy)
    if "npc_info" not in policy.get("names", {}):
        return None
    info = policy["names"]["npc_info"]
    if not isinstance(info, dict) or set(info) != NPC_INFO_FIELDS:
        raise ValueError("input names npc_info vocabulary")
    color, text = info["color"], info["text"]
    if type(color) is not int or not 0 <= color <= 0xFFFFFF:
        raise ValueError("input names npc_info colour")
    if not isinstance(text, str) or not 1 <= len(text) <= MAX_NPC_INFO \
            or any(not 32 <= ord(c) <= 126 for c in text) or text.count("{id}") != 1 \
            or set(without_state(text.replace("{id}", "\n", 1))) & set("{}"):
        raise ValueError("input names npc_info text")
    return u(color) + string(text)


def operator_chat(policy):
    """The cooked operator chat colour, or None without one."""
    names(policy)
    if "operator_chat" not in policy.get("names", {}):
        return None
    style = policy["names"]["operator_chat"]
    if not isinstance(style, dict) or set(style) != OPERATOR_CHAT_FIELDS:
        raise ValueError("input names operator_chat vocabulary")
    color = style["color"]
    if type(color) is not int or not 0 <= color <= 0xFFFFFF:
        raise ValueError("input names operator_chat colour")
    return u(color)


def without_state(text):
    """``text`` with its first state placeholder, ``{state}`` or
    ``{state:FALLBACK}`` (FALLBACK 1-16 printable ASCII bytes, no brace), cut
    out, as the client's ``npc_info_state`` finds it."""
    at = text.find("{state}")
    if at >= 0:
        return text[:at] + "\n" + text[at + 7:]
    at = text.find("{state:")
    close = text.find("}", at) if at >= 0 else -1
    if close < 0:
        return text
    fallback = text[at + 7:close]
    if not 1 <= len(fallback) <= 16 or set(fallback) & set("{}") \
            or any(not 32 <= ord(c) <= 126 for c in fallback):
        return text
    return text[:at] + "\n" + text[close + 1:]


def cook(policy):
    rows = flatten(policy)
    word, life, group, limits = names(policy), lifetime(policy), party(policy), distance(policy)
    npcs, info, operator = npc_lifetime(policy), npc_info(policy), operator_chat(policy)
    magic = (b"N3I1" if word is None else b"N3I8" if operator else b"N3I7" if info else b"N3I6" if npcs
             else b"N3I5" if limits else b"N3I4" if group else b"N3I2" if life is None else b"N3I3")
    out = magic + u(len(rows))
    for action, key, require, forbid, flags in rows:
        out += string(action) + string(key) + u(require) + u(forbid) + u(flags)
    if word is None:
        return out
    if operator:
        return (out + u(word) + (u(1) + life if life else u(0)) + (u(1) + group if group else u(0))
                + (limits or u(0)) + (u(1) + npcs if npcs else u(0)) + (u(1) + info if info else u(0))
                + operator)
    if info:
        return (out + u(word) + (u(1) + life if life else u(0)) + (u(1) + group if group else u(0))
                + (limits or u(0)) + (u(1) + npcs if npcs else u(0)) + info)
    if npcs:
        return (out + u(word) + (u(1) + life if life else u(0)) + (u(1) + group if group else u(0))
                + (limits or u(0)) + npcs)
    if limits:
        return (out + u(word) + (u(1) + life if life else u(0)) + (u(1) + group if group else u(0))
                + limits)
    if group:
        return out + u(word) + (u(1) + life if life else u(0)) + group
    return out + u(word) + (life or b"")
