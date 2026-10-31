"""Package input maps (PQ-009, D-136): vocabulary agreement, cooker and reader
validation, and the cooked KO and demo layouts."""
import json, os, re, shutil, struct, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path("tools/assetc").resolve()))
import input_map, main
from common import digest, string, u

# The cooker and the client must agree on every name.
header = Path("client/assets/input_names.h").read_text()


def names(array):
    body = re.search(array + r"\{(.*?)\};", header, re.S).group(1)
    return re.findall(r'"([^"]+)"', body)


assert names(r"action_names") == input_map.ACTIONS, "action vocabulary differs"
assert names(r"key_names") == input_map.KEYS, "key vocabulary differs"
assert names(r"reserved_keys") == list(input_map.RESERVED), "reserved keys differ"
assert names(r"modifier_names") == list(input_map.MODIFIERS), "modifier names differ"
held = re.search(r"held\(Action a\) \{ return a >= Action::(\w+) && a <= Action::(\w+);", header).groups()
first, last = input_map.ACTIONS.index(held[0]), input_map.ACTIONS.index(held[1])
assert set(input_map.ACTIONS[first:last + 1]) == input_map.HELD, "held actions differ"


def refused(policy, why):
    try:
        input_map.cook(policy)
    except ValueError:
        return
    raise AssertionError("cooker accepted " + why)


ok = {"action": "run_toggle", "keys": ["T"]}
for key in ("F12", "F11", "Grave"):
    refused({"bindings": [{"action": "run_toggle", "keys": [key]}]}, "a reserved key " + key)
refused({"bindings": [{"action": "fly", "keys": ["T"]}]}, "an unknown action")
refused({"bindings": [{"action": "run_toggle", "keys": ["F13"]}]}, "an unknown key")
refused({"bindings": [{**ok, "require": ["Alt"], "forbid": ["Alt"]}]}, "a contradictory modifier")
refused({"bindings": [{**ok, "require": ["Meta"]}]}, "an unknown modifier")
refused({"bindings": [ok, ok]}, "a duplicate binding")
refused({"bindings": [{**ok, "typing": 1}]}, "a non-boolean typing flag")
refused({"bindings": [{**ok, "extra": 1}]}, "an unknown field")
refused({"bindings": []}, "an empty table")
refused({"bindings": [{"action": "run_toggle", "keys": ["A", "B", "C", "D", "E"]}]}, "too many keys")
refused({"bindings": [{"action": a, "keys": [k]} for a in input_map.ACTIONS[:3] for k in input_map.KEYS[:43]]}, "too many bindings")
refused({"bindings": [ok], "other": 1}, "an unknown table field")
refused({"bindings": [{"action": "move_forward", "keys": ["MouseLeft"]}]}, "a mouse gesture on a held action")
refused({"bindings": [{"action": "attack_pick", "keys": ["MouseLeft"], "typing": True}]}, "a mouse gesture with the typing flag")
# Name display (PQ-014): shown at start plus a non-empty set of known classes.
for names_policy, why in [({"shown": 1, "hides": ["self"]}, "a non-boolean shown flag"),
                          ({"shown": True, "hides": []}, "a toggle that hides nothing"),
                          ({"shown": True, "hides": ["pets"]}, "an unknown class"),
                          ({"shown": True, "hides": ["self", "self"]}, "a repeated class"),
                          ({"shown": True}, "missing classes"),
                          ({"shown": True, "hides": ["self"], "saved": True}, "an unknown names field")]:
    refused({"bindings": [ok], "names": names_policy}, why)
assert input_map.cook({"bindings": [ok]})[:4] == b"N3I1", "a table without names keeps N3I1"
# Other-player label lifetime (PQ-169): measuring point, 0 < acquire <= release
# <= 1000 and known exempt classes.
life = {"from": "self", "acquire": 10, "release": 20, "exempt": ["party"]}
for change, why in [({"from": "eye"}, "an unknown measuring point"),
                    ({"acquire": 0}, "a zero acquire radius"),
                    ({"acquire": -1}, "a negative acquire radius"),
                    ({"acquire": 21}, "an acquire radius beyond the release radius"),
                    ({"release": 1001}, "a release radius beyond 1000 m"),
                    ({"release": float("inf")}, "an infinite release radius"),
                    ({"acquire": float("nan")}, "a NaN acquire radius"),
                    ({"acquire": True}, "a boolean radius"),
                    ({"acquire": "10"}, "a string radius"),
                    ({"exempt": ["clan"]}, "an unknown exempt class"),
                    ({"exempt": ["party", "party"]}, "a repeated exempt class"),
                    ({"exempt": "party"}, "an exempt string"),
                    ({"saved": True}, "an unknown lifetime field")]:
    refused({"bindings": [ok], "names": {"shown": True, "hides": ["self"], "lifetime": {**life, **change}}}, why)
partial = dict(life)
del partial["exempt"]
refused({"bindings": [ok], "names": {"shown": True, "hides": ["self"], "lifetime": partial}}, "a missing lifetime field")
refused({"bindings": [ok], "names": {"shown": True, "hides": ["self"], "lifetime": [10, 20]}}, "a lifetime list")
equal = input_map.cook({"bindings": [ok], "names": {"shown": True, "hides": ["self"],
                                                  "lifetime": {**life, "acquire": 20, "from": "camera", "exempt": []}}})
assert equal[:4] == b"N3I3" and equal[-16:] == u(1) + struct.pack("<2f", 20, 20) + u(0), "equal radii, camera, no exemption"

# Party names (PQ-166): two boolean flags and an optional 0xRRGGBB colour.
group = {"while_hidden": True, "beyond_distance": True, "color": 0xFFFF00}
for change, why in [({"while_hidden": 1}, "a non-boolean while_hidden"),
                    ({"beyond_distance": "yes"}, "a non-boolean beyond_distance"),
                    ({"color": 0x1000000}, "a colour beyond 24 bits"),
                    ({"color": -1}, "a negative colour"),
                    ({"color": True}, "a boolean colour"),
                    ({"color": "ffff00"}, "a string colour"),
                    ({"color": 1.5}, "a fractional colour"),
                    ({"saved": True}, "an unknown party field")]:
    refused({"bindings": [ok], "names": {"shown": True, "hides": ["players"], "party": {**group, **change}}}, why)
partial = dict(group)
del partial["beyond_distance"]
refused({"bindings": [ok], "names": {"shown": True, "hides": ["players"], "party": partial}}, "a missing party field")
refused({"bindings": [ok], "names": {"shown": True, "hides": ["players"], "party": True}}, "a party flag")
plain = input_map.cook({"bindings": [ok], "names": {"shown": True, "hides": ["players"],
                                                  "party": {"while_hidden": False, "beyond_distance": True}}})
assert plain[:4] == b"N3I4" and plain[-16:] == u(0b0101) + u(0) + u(0b010) + u(0), "party without lifetime or colour"
both = input_map.cook({"bindings": [ok], "names": {"shown": False, "hides": ["players"], "lifetime": life, "party": group}})
assert both[:4] == b"N3I4" and both[-32:] == u(0b0100) + u(1) + u(0) + struct.pack("<2f", 10, 20) + u(1) + u(0b111) + u(0xFFFF00), \
    "party after the lifetime record"

# Camera distance by class (PQ-173): known classes, 0 < limit <= 1000, finite numbers.
for limits, why in [({}, "an empty distance"),
                    ({"pets": 33}, "an unknown class"),
                    ({"players": 0}, "a zero limit"),
                    ({"players": -1}, "a negative limit"),
                    ({"players": 1001}, "a limit beyond 1000 m"),
                    ({"players": float("inf")}, "an infinite limit"),
                    ({"players": float("nan")}, "a NaN limit"),
                    ({"players": True}, "a boolean limit"),
                    ({"players": "33"}, "a string limit"),
                    ([33], "a distance list")]:
    refused({"bindings": [ok], "names": {"shown": True, "hides": ["players"], "distance": limits}}, why)
only = input_map.cook({"bindings": [ok], "names": {"shown": True, "hides": ["players"], "distance": {"players": 33}}})
assert only[:4] == b"N3I5" and only[-20:] == u(0b0101) + u(0) + u(0) + u(0b010) + struct.pack("<f", 33), \
    "distance without lifetime or party"
every = input_map.cook({"bindings": [ok], "names": {"shown": True, "hides": ["players"], "lifetime": life, "party": group,
                                                   "distance": {"npcs": 50, "self": 1000, "players": .5}}})
assert every[:4] == b"N3I5" and every[-52:] == u(0b0101) + u(1) + u(0) + struct.pack("<2f", 10, 20) + u(1) + u(1) \
    + u(0b111) + u(0xFFFF00) + u(0b111) + struct.pack("<3f", 1000, .5, 50), "limits in class order after the party record"

# NPC label lifetime (PQ-174): measuring point, 0 < acquire <= release <= 1000,
# a known release rule and two boolean flags, every field required.
npc_life = {"from": "self", "acquire": 10, "release": 20, "rule": "band", "always": False, "drop_dead": True}
for change, why in [({"from": "eye"}, "an unknown NPC measuring point"),
                    ({"acquire": 0}, "a zero NPC acquire radius"),
                    ({"acquire": 21}, "an NPC acquire radius beyond the release radius"),
                    ({"release": 1001}, "an NPC release radius beyond 1000 m"),
                    ({"release": float("inf")}, "an infinite NPC release radius"),
                    ({"acquire": float("nan")}, "a NaN NPC acquire radius"),
                    ({"acquire": True}, "a boolean NPC radius"),
                    ({"rule": "above"}, "an unknown NPC release rule"),
                    ({"always": 1}, "a non-boolean always flag"),
                    ({"drop_dead": "yes"}, "a non-boolean drop_dead flag"),
                    ({"exempt": ["party"]}, "an unknown NPC lifetime field")]:
    refused({"bindings": [ok], "names": {"shown": True, "hides": ["players"], "npc_lifetime": {**npc_life, **change}}}, why)
partial = dict(npc_life)
del partial["drop_dead"]
refused({"bindings": [ok], "names": {"shown": True, "hides": ["players"], "npc_lifetime": partial}}, "a missing NPC lifetime field")
refused({"bindings": [ok], "names": {"shown": True, "hides": ["players"], "npc_lifetime": [10, 20]}}, "an NPC lifetime list")
alone = input_map.cook({"bindings": [ok], "names": {"shown": True, "hides": ["players"], "npc_lifetime": npc_life}})
assert alone[:4] == b"N3I6" and alone[-32:] == u(0b0101) + u(0) + u(0) + u(0) + u(0) + struct.pack("<2f", 10, 20) \
    + u(0b101), "NPC lifetime alone: no lifetime, party or limits, then the record"
full = input_map.cook({"bindings": [ok], "names": {"shown": True, "hides": ["players"], "lifetime": life, "party": group,
                                                  "distance": {"npcs": 50},
                                                  "npc_lifetime": {**npc_life, "from": "camera", "rule": "beyond",
                                                                   "always": True, "drop_dead": False}}})
assert full[:4] == b"N3I6" and full[-60:] == u(0b0101) + u(1) + u(0) + struct.pack("<2f", 10, 20) + u(1) + u(1) \
    + u(0b111) + u(0xFFFF00) + u(0b100) + struct.pack("<f", 50) + u(1) + struct.pack("<2f", 10, 20) + u(0b010), \
    "NPC record after the limits"

# NPC info line (PQ-177): a colour 0..0xFFFFFF and 1-64 printable ASCII bytes
# with exactly one {id}, at most one {state} or {state:FALLBACK} (PQ-186) and no
# other brace, both fields required.
npc_info = {"color": 0x00FF00, "text": "ID({id}) : TYPE(0)"}
for change, why in [({"color": -1}, "a negative info colour"), ({"color": 0x1000000}, "an info colour beyond RGB"),
                    ({"color": True}, "a boolean info colour"), ({"color": 1.0}, "a float info colour"),
                    ({"text": ""}, "an empty info line"), ({"text": "x" * 61 + "{id}"}, "an info line over 64 bytes"),
                    ({"text": "ID(n)"}, "an info line without {id}"), ({"text": "{id}{id}"}, "two {id}"),
                    ({"text": "ID({id}) {"}, "a stray brace"), ({"text": "ID({ID})"}, "an unknown placeholder"),
                    ({"text": "ID({id})\n"}, "a control character"), ({"text": "ID({id}) \u00e9"}, "non-ASCII text"),
                    ({"text": 5}, "a non-string info line"), ({"capability": "server.inspect"}, "a package capability"),
                    ({"text": "TYPE({state})"}, "{state} without {id}"),
                    ({"text": "{id}{state}{state}"}, "two {state}"), ({"text": "{id}{STATE}"}, "an upper-case {STATE}"),
                    ({"text": "{id}{state"}, "an unclosed {state"), ({"text": "{{id}}"}, "braces around {id}"),
                    ({"text": "{sta{id}te}"}, "a {state} split by {id}"),
                    ({"text": "{id}{state:}"}, "an empty fallback"), ({"text": "{id}{state:" + "x" * 17 + "}"}, "a fallback over 16 bytes"),
                    ({"text": "{state:{id}}"}, "{id} inside a fallback"), ({"text": "{id}{state:0}{state}"}, "two state placeholders"),
                    ({"text": "{id}{state:0"}, "an unclosed fallback")]:
    refused({"bindings": [ok], "names": {"shown": True, "hides": ["players"], "npc_info": {**npc_info, **change}}}, why)
refused({"bindings": [ok], "names": {"shown": True, "hides": ["players"], "npc_info": {"text": "{id}"}}}, "a missing info colour")
refused({"bindings": [ok], "names": {"shown": True, "hides": ["players"], "npc_info": ["{id}"]}}, "an info line list")
assert input_map.cook({"bindings": [ok], "names": {"shown": True, "hides": ["players"],
                                                  "npc_info": {**npc_info, "text": "x" * 60 + "{id}"}}})[:4] == b"N3I7"
for text in ["ID({id}) : TYPE({state})", "{state}{id}", "{id}{state}", "ID({id}) : TYPE({state:0})",
             "{id}{state:" + "x" * 16 + "}", "{state:n/a}{id}"]:
    assert input_map.cook({"bindings": [ok], "names": {"shown": True, "hides": ["players"],
                                                      "npc_info": {**npc_info, "text": text}}}).endswith(string(text)), text
info_alone = input_map.cook({"bindings": [ok], "names": {"shown": True, "hides": ["players"], "npc_info": npc_info}})
assert info_alone[:4] == b"N3I7" and info_alone.endswith(u(0b0101) + u(0) + u(0) + u(0) + u(0) + u(0x00FF00)
                                                         + string("ID({id}) : TYPE(0)")), \
    "info line alone: no lifetime, party, limits or NPC lifetime, then colour and text"
info_full = input_map.cook({"bindings": [ok], "names": {"shown": True, "hides": ["players"], "lifetime": life,
                                                       "party": group, "distance": {"npcs": 50},
                                                       "npc_lifetime": npc_life, "npc_info": npc_info}})
assert info_full[:4] == b"N3I7" and info_full.endswith(
    u(0b0101) + u(1) + u(0) + struct.pack("<2f", 10, 20) + u(1) + u(1) + u(0b111) + u(0xFFFF00) + u(0b100)
    + struct.pack("<f", 50) + u(1) + u(0) + struct.pack("<2f", 10, 20) + u(0b101) + u(0x00FF00)
    + string("ID({id}) : TYPE(0)")), "info line after the NPC lifetime record"

# Operator chat colour (PQ-178): one colour 0..0xFFFFFF, nothing else; the
# table styles a line the server marked and has no way to mark one.
for style, why in [({"color": -1}, "a negative operator colour"), ({"color": 0x1000000}, "an operator colour beyond RGB"),
                   ({"color": True}, "a boolean operator colour"), ({"color": 1.0}, "a float operator colour"),
                   ({}, "a missing operator colour"), ({"color": 1, "capability": "server.inspect"}, "a package capability"),
                   ({"color": 1, "types": [1]}, "an extra operator field"), ([0xCD9BFF], "an operator style list")]:
    refused({"bindings": [ok], "names": {"shown": True, "hides": ["players"], "operator_chat": style}}, why)
operator_alone = input_map.cook({"bindings": [ok], "names": {"shown": True, "hides": ["players"],
                                                            "operator_chat": {"color": 0xCD9BFF}}})
assert operator_alone[:4] == b"N3I8" and operator_alone.endswith(u(0b0101) + u(0) + u(0) + u(0) + u(0) + u(0)
                                                                 + u(0xCD9BFF)), \
    "operator colour alone: no lifetime, party, limits, NPC lifetime or info line, then the colour"
operator_info = input_map.cook({"bindings": [ok], "names": {"shown": True, "hides": ["players"], "npc_info": npc_info,
                                                           "operator_chat": {"color": 0}}})
assert operator_info[:4] == b"N3I8" and operator_info.endswith(u(1) + u(0x00FF00) + string("ID({id}) : TYPE(0)") + u(0)), \
    "operator colour after the flagged info line"

# The KO table matches the binary handler (005c6990): what it binds and what it lacks.
ko = json.loads(Path("games/moradon/input.json").read_text())
rows = input_map.flatten(ko)
bound = {(a, k) for a, k, _, _, _ in rows}
for action, key in [("run_toggle", "T"), ("auto_move", "E"), ("attack_toggle", "R"), ("target_enemy", "Z"),
                    ("target_party", "X"), ("target_npc", "B"), ("character", "U"), ("command_list", "H"),
                    ("names_toggle", "O"), ("help", "F10"), ("hotbar_page_prev", "PageUp"),
                    ("hotbar_page_next", "PageDown"), ("move_forward", "Up"), ("move_backward", "Down"),
                    ("turn_left", "Left"), ("turn_right", "Right"), ("chat", "KeypadEnter"),
                    ("cancel", "Escape")]:
    assert (action, key) in bound, (action, key)
assert not {k for _, k in bound} & {"F", "V", "Tab", "Space", "F11", "F12"}, "KO has no gameplay handler for these keys"
# PQ-012: Home/End pitch while held (005c6990 DIK 0xc7/0xcf), blocked while typing (no typing flag).
assert ("camera_pitch_up", "Home", 0, 0, 0) in rows and ("camera_pitch_down", "End", 0, 0, 0) in rows
for i in range(1, 9):
    assert (f"hotbar_page_{i}", f"F{i}", 0, 8, 1) in rows, f"F{i} must need Alt up and work while typing"
enter = [a for a, k, _, _, _ in rows if k == "Return"]
assert enter == ["respawn", "chat"], enter
# PQ-011: Ctrl+left press (either Ctrl, 005e16f0) and the left double click (005e1490).
ctrl = 1 << input_map.MODIFIERS.index("Ctrl")
assert ("attack_pick", "MouseLeft", ctrl, 0, 0) in rows and ("attack_target", "MouseLeftDouble", 0, 0, 0) in rows
# PQ-014: O flips the name display (005c6990, 006d42e4); on at start (static 1);
# it hides self (0046b5a0) and other players (0046ea90), never NPCs (00459820).
assert input_map.names(ko) == 0b0111, input_map.names(ko)
# PQ-169: KO's player-manager tick 00470900 builds other players' labels below
# 10.0 (006a425c) and frees them above 20.0 (006a4260), measured from the local
# player's position ([00818794]+0x98), party members (+0x7dc) exempt.
assert ko["names"]["lifetime"] == {"from": "self", "acquire": 10, "release": 20, "exempt": ["party"]}, ko["names"]
# PQ-166: the party marker (+0x7dc) keeps a member's name under O and beyond
# 48 m (0046ea90; Moradon's Zones.tbl row 210 column 23 is 1, set by the KO bake)
# and draws it 0xffffff00 (0046e840).
assert ko["names"]["party"] == {"while_hidden": True, "beyond_distance": True, "color": 0xFFFF00}, ko["names"]
# PQ-174: KO's manager tick 00470900 builds an NPC's name below 10.0 of the
# local player's position, frees it while 10.0 <= d < 20.0 (00470be0) and keeps
# it at 20.0 or farther; a dead NPC (state 5) loses it. `always` comes from the
# template's NPC_Looks row (ko_bake.npc_names); the source table says false.
assert ko["names"]["npc_lifetime"] == npc_life, ko["names"]
# PQ-177: KO's NPC label refresh 00465070 formats "ID(%d) : TYPE(%d)"
# (006d44f0) in 0xff00ff00; TYPE is 0 until opcode 0x5d sets the byte. PQ-186:
# the byte is the AI state reported for an NPC an operator traced; n3e shows the
# server's state for a traced NPC through {state:0}, whose fallback 0 is KO's
# initial byte (D-147).
assert ko["names"]["npc_info"] == {**npc_info, "text": "ID({id}) : TYPE({state:0})"}, ko["names"]
# PQ-178: KO's chat handler 005cac80 sets 0xffcd9bff (005cb2f5) for an
# operator's line of any type but 7.
assert ko["names"]["operator_chat"] == {"color": 0xCD9BFF}, ko["names"]
cooked = input_map.cook(ko)
assert cooked[:4] == b"N3I8" and cooked.endswith(u(0b0111) + u(1) + u(0) + struct.pack("<2f", 10, 20) + u(1)
                                                 + u(1) + u(0b111) + u(0xFFFF00) + u(0) + u(1) + u(0)
                                                 + struct.pack("<2f", 10, 20) + u(0b101) + u(1) + u(0x00FF00)
                                                 + string("ID({id}) : TYPE({state:0})") + u(0xCD9BFF)), \
    "KO table cooks the name display word, the label lifetime, the party names, the NPC label lifetime, " \
    "the info line and the operator chat colour"
without = lambda *keys: {**ko, "names": {k: v for k, v in ko["names"].items() if k not in keys}}
assert input_map.cook(without("party", "npc_lifetime", "npc_info", "operator_chat"))[:4] == b"N3I3", \
    "a lifetime without party names keeps N3I3"
assert input_map.cook(without("npc_lifetime", "npc_info", "operator_chat"))[:4] == b"N3I4", \
    "party names without an NPC lifetime keep N3I4"
assert input_map.cook(without("npc_info", "operator_chat"))[:4] == b"N3I6", "an NPC lifetime without the info line keeps N3I6"
assert input_map.cook(without("operator_chat"))[:4] == b"N3I7", "the info line without the operator colour keeps N3I7"

# PQ-173: the KO bake sets the zone-dependent name rules from the package's
# Zones.tbl row (ko_bake.zone_names). 0046ea90 compares other players with 33.0
# (006a4250) instead of 48.0 (006a40dc) when the zone key (0046c9d0) is 0x140;
# it skips the limit for the party marker unless column 23 is 0 (PQ-166).
import copy, csv, ko_bake
zone_distance = json.loads(Path("games/moradon/nameplates.json").read_text())["zone_distance"]
assert zone_distance == {"320": {"players": 33}} and 0x140 == 320, zone_distance


def baked(row, policy=ko):
    out = copy.deepcopy(policy)
    return out, ko_bake.zone_names(row, out, zone_distance)


row = lambda key, column_23: [str(key), "Zones\\x.gtd"] + [""] * 20 + [column_23]
moradon, report = baked(row(210, "1"))
assert moradon == ko and report == {"party_names": {"zone_key": 210, "column_23": 1, "beyond_distance": True},
                                    "name_distance": {"zone_key": 210, "distance": {}}}, report
dungeon, report = baked(row(320, "0"))
assert dungeon["names"]["distance"] == {"players": 33} and not dungeon["names"]["party"]["beyond_distance"], dungeon
assert report["name_distance"] == {"zone_key": 320, "distance": {"players": 33}}, report
key320 = input_map.cook(dungeon)
assert key320[:4] == b"N3I8" and key320.endswith(
    u(0b0111) + u(1) + u(0) + struct.pack("<2f", 10, 20) + u(1) + u(1) + u(0b101) + u(0xFFFF00) + u(0b010)
    + struct.pack("<f", 33) + u(1) + u(0) + struct.pack("<2f", 10, 20) + u(0b101) + u(1) + u(0x00FF00)
    + string("ID({id}) : TYPE({state:0})") + u(0xCD9BFF)), "key 320 cooks the other-player limit"
# Another zone drops a stale limit; a short row or a non-integer column 23
# counts as 1 (0046ea90); a table without names or party is left alone.
again, _ = baked(row(330, "0"), dungeon)
assert "distance" not in again["names"] and not again["names"]["party"]["beyond_distance"], again
short, report = baked(["320", "Zones\\x.gtd"])
assert short["names"]["party"]["beyond_distance"] and short["names"]["distance"] == {"players": 33}, short
assert report["party_names"]["column_23"] == 1, report
assert baked(row(210, "x"))[1]["party_names"]["column_23"] == 1
bare = {"bindings": [ok]}
assert baked(row(320, "0"), bare)[0] == bare, "no names policy: nothing to set"
# The local-asset rows, when the reference table is present.
table = Path("assets/ko/Data/Zones.tbl.csv")
if table.exists():
    rows = {r[1].lower(): r for r in list(csv.reader(table.open(encoding="utf-8", errors="replace")))[1:]}
    assert baked(rows["zones\\moradon_xmas.gtd"])[0] == ko, "Moradon (key 210): no zone limit"
    real, report = baked(rows["zones\\dungeon_b1th.gtd"])
    assert real == dungeon and report["name_distance"]["zone_key"] == 320, report
    print("PASS Zones.tbl rows: Moradon key 210 keeps 48 m and the party skip; dungeon_b1th key 320 gets 33 m for players, no party skip")
else:
    print("SKIP Zones.tbl rows: assets/ko/Data/Zones.tbl.csv not present")

# PQ-174: the KO bake sets the NPC looks flag from the template's NPC_Looks row
# (sPid; NPC-in reads the looks key at 005cd699, NPC_Looks lookup 005cdc58):
# column 36 (row +0x14c) = 1 keeps the name at any range (00470baa) and skips
# the 48 m limit (00459856).
worm = {"sSid": 750, "sPid": 700}


def looks_baked(rows, policy=ko, monster=worm):
    out = copy.deepcopy(policy)
    return out, ko_bake.npc_names([["1 - UInt32"]] + rows, monster, out)


looks_row = lambda pid, column_36: [str(pid)] + [""] * 34 + [column_36, "0", "100"]
plain_worm, report = looks_baked([looks_row(700, "0")])
assert plain_worm == ko and report == {"npc_names": {"template": 750, "looks": 700, "looks_row": True, "column_36": 0,
                                                     "always": False}}, report
flagged, report = looks_baked([looks_row(699, "0"), looks_row(700, "1")])
assert flagged["names"]["npc_lifetime"]["always"] and report["npc_names"]["column_36"] == 1, report
assert input_map.cook(flagged).endswith(u(0b111) + u(1) + u(0x00FF00) + string("ID({id}) : TYPE({state:0})")
                                        + u(0xCD9BFF)), \
    "a flagged template cooks the always bit"
missing, report = looks_baked([looks_row(701, "1")], flagged)
assert not missing["names"]["npc_lifetime"]["always"] and not report["npc_names"]["looks_row"], report
assert not looks_baked([looks_row(700, "x")], flagged)[0]["names"]["npc_lifetime"]["always"], "a non-integer value counts as 0"
assert not looks_baked([["700", "short"]], flagged)[0]["names"]["npc_lifetime"]["always"], "a short row counts as 0"
assert looks_baked([looks_row(700, "1")], bare)[0] == bare, "no names policy: nothing to set"
reference = json.loads(Path("games/moradon/ko-reference.json").read_text())["monster"]
assert reference["sSid"] == 750 and reference["sPid"] == 700, reference
table = Path("assets/ko/Data/NPC_Looks.tbl.csv")
if table.exists():
    rows = list(csv.reader(table.open(encoding="utf-8-sig", errors="replace")))
    assert rows[0][35].startswith("36 - Byte") and len(rows[0]) == 38, rows[0]
    real_policy = copy.deepcopy(ko)
    report = ko_bake.npc_names(rows, reference, real_policy)
    assert real_policy == ko and report["npc_names"]["looks_row"] and report["npc_names"]["column_36"] == 0, report
    worm_row = next(r for r in rows[1:] if r[0] == "700")
    assert worm_row[2].lower() == "chr\\mob_worm.n3joint", worm_row[2]
    priest = copy.deepcopy(ko)
    ko_bake.npc_names(rows, {"sSid": 2060, "sPid": 2060}, priest)
    assert priest["names"]["npc_lifetime"]["always"], "the Moradon priest (looks 2060) is named at any range"
    assert sum(1 for r in rows[1:] if r[35] == "1") == 30, "30 of 163 looks rows carry the flag (PQ-170)"
    print("PASS NPC_Looks rows: worm looks 700 (chr\\mob_worm.n3joint) column 36 = 0; priest 2060 flagged; 30 flagged rows")
else:
    print("SKIP NPC_Looks rows: assets/ko/Data/NPC_Looks.tbl.csv not present")


def readers(out, client=True, server=True):
    for command, good in [(["build/client/n3e-asset-check", str(out)], client),
                          (["target/debug/n3e-server", "--check-content"], server)]:
        p = subprocess.run(command, env={**os.environ, "N3E_PACKAGE": str(out)}, capture_output=True, text=True)
        assert (p.returncode == 0) == good, (command, p.stdout, p.stderr)


def rehash(out, name, data):
    """Rewrite one cooked file and the release index, so readers reach the parser."""
    (out / name).write_bytes(data)
    raw = (out / "release.bin").read_bytes()
    at = 16
    for _ in range(2):
        n = struct.unpack_from("<I", raw, at)[0]
        at += 4 + n
    head, count = raw[:at], struct.unpack_from("<I", raw, at)[0]
    at += 4
    entries = []
    for _ in range(count):
        n = struct.unpack_from("<I", raw, at)[0]
        at += 4
        key = raw[at:at + n].decode()
        at += n + 36
        content = (out / key).read_bytes()
        entries.append(string(key) + u(len(content)) + digest(content))
    (out / "release.bin").write_bytes(head + u(count) + b"".join(entries))


def binding(action, key, require=0, forbid=0, flags=0):
    return b"N3I1" + u(1) + string(action) + string(key) + u(require) + u(forbid) + u(flags)


demo = Path("build/packages/demo")
assert (demo / "input.bin").exists(), "make assets cooks the demo input map"
readers(demo)
subprocess.run(["build/client/n3e-input-check", str(demo), "demo"], check=True)

with tempfile.TemporaryDirectory(dir="build") as tmp:
    source, out = Path(tmp) / "source", Path(tmp) / "release"
    shutil.copytree("games/demo", source)
    manifest = json.loads((source / "package.json").read_text())
    manifest["input"] = ko
    (source / "package.json").write_text(json.dumps(manifest))
    main.cook(source, out)
    readers(out)
    subprocess.run(["build/client/n3e-input-check", str(out), "ko"], check=True)
    # The client refuses a table it cannot honour; the server only checks the magic.
    for data in [binding("fly", "T"), binding("run_toggle", "F12"), binding("run_toggle", "T", 1, 1),
                 binding("run_toggle", "T", 0, 0, 2), binding("run_toggle", "T") + b"\0",
                 b"N3I1" + u(0), b"N3I1" + u(129), binding("move_forward", "MouseLeft"),
                 binding("attack_pick", "MouseLeft", 0, 0, 1)]:
        main.cook(source, out)
        rehash(out, "input.bin", data)
        readers(out, client=False, server=True)
    # N3I2 (PQ-014): the client refuses a word with unknown bits or no class.
    for word in (0, 1, 0x11, 0x80000003):
        main.cook(source, out)
        rehash(out, "input.bin", b"N3I2" + binding("run_toggle", "T")[4:] + u(word))
        readers(out, client=False, server=True)
    main.cook(source, out)
    rehash(out, "input.bin", b"N3I2" + binding("run_toggle", "T")[4:])
    readers(out, client=False, server=True)
    main.cook(source, out)
    rehash(out, "input.bin", b"N3I2" + binding("run_toggle", "T")[4:] + u(0b1001))
    readers(out)
    main.cook(source, out)
    rehash(out, "input.bin", b"N3I0" + binding("run_toggle", "T")[4:])
    readers(out, client=False, server=False)
    rehash(out, "input.bin", b"N3I9" + binding("run_toggle", "T")[4:] + u(0b1001))
    readers(out, client=False, server=False)
    # N3I3 (PQ-169): the client refuses a lifetime it cannot honour; the server
    # accepts the magic.
    def n3i3(record):
        return b"N3I3" + binding("run_toggle", "T")[4:] + u(0b0111) + record
    def record(frm=0, acquire=10, release=20, exempt=1):
        return u(frm) + struct.pack("<2f", acquire, release) + u(exempt)
    for bad in [b"", record()[:-1], record(frm=2), record(acquire=0), record(acquire=-1), record(acquire=21),
                record(release=1001), record(acquire=float("nan")), record(release=float("inf")),
                record(exempt=2), record(exempt=0x80000001), record() + b"\0"]:
        main.cook(source, out)
        rehash(out, "input.bin", n3i3(bad))
        readers(out, client=False, server=True)
    for good in [record(), record(frm=1, acquire=20, release=20, exempt=0), record(acquire=.5, release=1000)]:
        main.cook(source, out)
        rehash(out, "input.bin", n3i3(good))
        readers(out)
    # N3I4 (PQ-166): lifetime flag 0 or 1 (then the record), party flags and
    # colour. The client refuses what it cannot honour; the server accepts the magic.
    def n3i4(flag, rest, flags=0b111, color=0xFFFF00):
        return b"N3I4" + binding("run_toggle", "T")[4:] + u(0b0111) + u(flag) + rest + u(flags) + u(color)
    for bad in [n3i4(2, b""), n3i4(1, b""), n3i4(0, b"", flags=0b1000), n3i4(0, b"", color=0x1000000),
                n3i4(0, b"", flags=0b011, color=5), n3i4(1, record(acquire=0)), n3i4(0, b"")[:-1],
                n3i4(0, b"") + b"\0", n3i4(0, record())]:
        main.cook(source, out)
        rehash(out, "input.bin", bad)
        readers(out, client=False, server=True)
    for good in [n3i4(0, b""), n3i4(1, record()), n3i4(0, b"", flags=0, color=0), n3i4(1, record(), flags=0b100, color=0)]:
        main.cook(source, out)
        rehash(out, "input.bin", good)
        readers(out)
    # N3I5 (PQ-173): lifetime and party flags with their records, then the
    # class mask and one limit per set bit. The client refuses what it cannot
    # honour; the server accepts the magic.
    def n3i5(life_flag, life_rest, party_flag, party_rest, mask, limits):
        return (b"N3I5" + binding("run_toggle", "T")[4:] + u(0b0111) + u(life_flag) + life_rest + u(party_flag)
                + party_rest + u(mask) + struct.pack(f"<{len(limits)}f", *limits))
    group_record = u(0b111) + u(0xFFFF00)
    for bad in [n3i5(0, b"", 0, b"", 0, []), n3i5(0, b"", 0, b"", 0b1000, [33]), n3i5(0, b"", 0, b"", 0b010, [0]),
                n3i5(0, b"", 0, b"", 0b010, [-1]), n3i5(0, b"", 0, b"", 0b010, [1001]),
                n3i5(0, b"", 0, b"", 0b010, [float("nan")]), n3i5(0, b"", 0, b"", 0b010, [float("inf")]),
                n3i5(0, b"", 0, b"", 0b011, [33]), n3i5(0, b"", 0, b"", 0b010, [33, 48]),
                n3i5(0, b"", 2, b"", 0b010, [33]), n3i5(0, b"", 1, u(0b1000) + u(0), 0b010, [33]),
                n3i5(2, b"", 0, b"", 0b010, [33]), n3i5(1, record(acquire=0), 0, b"", 0b010, [33]),
                n3i5(0, b"", 0, b"", 0b010, [33])[:-1]]:
        main.cook(source, out)
        rehash(out, "input.bin", bad)
        readers(out, client=False, server=True)
    for good in [n3i5(0, b"", 0, b"", 0b010, [33]), n3i5(1, record(), 1, group_record, 0b010, [33]),
                 n3i5(0, b"", 1, group_record, 0b111, [1000, .5, 48])]:
        main.cook(source, out)
        rehash(out, "input.bin", good)
        readers(out)
    # N3I6 (PQ-174): the N3I5 layout (class mask may be 0), then the NPC
    # record. The client refuses what it cannot honour; the server accepts the magic.
    def n3i6(mask, limits, npc):
        return n3i5(0, b"", 0, b"", mask, limits).replace(b"N3I5", b"N3I6", 1) + npc
    def npc_record(frm=0, acquire=10, release=20, flags=0b101):
        return u(frm) + struct.pack("<2f", acquire, release) + u(flags)
    for bad in [n3i6(0, [], b""), n3i6(0, [], npc_record()[:-1]), n3i6(0, [], npc_record(frm=2)),
                n3i6(0, [], npc_record(acquire=0)), n3i6(0, [], npc_record(acquire=21)),
                n3i6(0, [], npc_record(release=1001)), n3i6(0, [], npc_record(acquire=float("nan"))),
                n3i6(0, [], npc_record(release=float("inf"))), n3i6(0, [], npc_record(flags=0b1000)),
                n3i6(0b1000, [33], npc_record()), n3i6(0, [], npc_record()) + b"\0"]:
        main.cook(source, out)
        rehash(out, "input.bin", bad)
        readers(out, client=False, server=True)
    for good in [n3i6(0, [], npc_record()), n3i6(0b100, [50], npc_record(frm=1, acquire=20, release=20, flags=0b010)),
                 n3i6(0, [], npc_record(acquire=.5, release=1000, flags=0))]:
        main.cook(source, out)
        rehash(out, "input.bin", good)
        readers(out)
    # N3I7 (PQ-177): the N3I5 layout (class mask may be 0), the NPC lifetime
    # flag and record, then the info line. The client refuses what it cannot
    # honour; the server accepts the magic.
    def n3i7(mask, limits, npc_flag, npc, color, text):
        return (n3i5(0, b"", 0, b"", mask, limits).replace(b"N3I5", b"N3I7", 1) + u(npc_flag) + npc + u(color)
                + (string(text) if isinstance(text, str) else text))
    for bad in [n3i7(0, [], 0, b"", 0x00FF00, ""), n3i7(0, [], 0, b"", 0x00FF00, "ID(n)"),
                n3i7(0, [], 0, b"", 0x00FF00, "{id}{id}"), n3i7(0, [], 0, b"", 0x00FF00, "{id} }"),
                n3i7(0, [], 0, b"", 0x00FF00, "x" * 61 + "{id}"), n3i7(0, [], 0, b"", 0x00FF00, u(5) + b"{id}\n"),
                n3i7(0, [], 0, b"", 0x00FF00, u(5) + b"{id}\xe9"), n3i7(0, [], 0, b"", 0x1000000, "{id}"),
                n3i7(0, [], 2, b"", 0x00FF00, "{id}"), n3i7(0, [], 1, b"", 0x00FF00, "{id}"),
                n3i7(0, [], 1, npc_record(acquire=0), 0x00FF00, "{id}"), n3i7(0, [], 0, b"", 0x00FF00, "{id}")[:-1],
                n3i7(0, [], 0, b"", 0x00FF00, "{id}") + b"\0", n3i7(0, [], 0, b"", 0x00FF00, b""),
                n3i7(0, [], 0, b"", 0x00FF00, "{state}"), n3i7(0, [], 0, b"", 0x00FF00, "{id}{state}{state}"),
                n3i7(0, [], 0, b"", 0x00FF00, "{sta{id}te}"), n3i7(0, [], 0, b"", 0x00FF00, "{{id}}"),
                n3i7(0, [], 0, b"", 0x00FF00, "{id}{state:}"), n3i7(0, [], 0, b"", 0x00FF00, "{state:{id}}")]:
        main.cook(source, out)
        rehash(out, "input.bin", bad)
        readers(out, client=False, server=True)
    for good in [n3i7(0, [], 0, b"", 0x00FF00, "{id}"), n3i7(0b100, [50], 1, npc_record(), 0, "ID({id}) : TYPE(0)"),
                 n3i7(0, [], 0, b"", 0xFFFFFF, "x" * 60 + "{id}"), n3i7(0, [], 0, b"", 0x00FF00, "ID({id}) : TYPE({state})"),
                 n3i7(0, [], 0, b"", 0x00FF00, "ID({id}) : TYPE({state:0})")]:
        main.cook(source, out)
        rehash(out, "input.bin", good)
        readers(out)
    # N3I8 (PQ-178): the N3I7 layout with a flag before the info line, then
    # the operator chat colour. The client refuses what it cannot honour; the
    # server accepts the magic.
    def n3i8(info_flag, info, color):
        return n3i5(0, b"", 0, b"", 0, []).replace(b"N3I5", b"N3I8", 1) + u(0) + u(info_flag) + info + u(color)
    info_record = u(0x00FF00) + string("ID({id}) : TYPE(0)")
    for bad in [n3i8(0, b"", 0x1000000), n3i8(2, b"", 0xCD9BFF), n3i8(1, b"", 0xCD9BFF),
                n3i8(1, u(0x00FF00) + string("ID(n)"), 0xCD9BFF), n3i8(0, b"", 0xCD9BFF)[:-1],
                n3i8(0, b"", 0xCD9BFF) + b"\0", n3i8(0, info_record, 0xCD9BFF)]:
        main.cook(source, out)
        rehash(out, "input.bin", bad)
        readers(out, client=False, server=True)
    for good in [n3i8(0, b"", 0xCD9BFF), n3i8(1, info_record, 0), n3i8(0, b"", 0xFFFFFF)]:
        main.cook(source, out)
        rehash(out, "input.bin", good)
        readers(out)
    # The KO table as the bake writes it for key 320 cooks and loads.
    manifest["input"] = dungeon
    (source / "package.json").write_text(json.dumps(manifest))
    main.cook(source, out)
    readers(out)
    subprocess.run(["build/client/n3e-input-check", str(out), "ko-key320"], check=True)
    manifest["input"] = ko
    (source / "package.json").write_text(json.dumps(manifest))
    # A good N3I2 still loads (no lifetime: every other player keeps a label).
    main.cook(source, out)
    rehash(out, "input.bin", b"N3I2" + binding("run_toggle", "T")[4:] + u(0b0111))
    readers(out)
    # Without a table the release keeps working (legacy layout).
    del manifest["input"]
    (source / "package.json").write_text(json.dumps(manifest))
    main.cook(source, out)
    assert not (out / "input.bin").exists()
    readers(out)
print("PASS input map vocabularies agree, cooker refuses reserved/unknown/duplicate bindings, "
      "client fails closed, server checks magic, KO and demo layouts cooked, KO name display policy, label lifetime, party names, "
      "the key-320 other-player camera limit, the NPC label lifetime, the NPC info line and the operator chat colour")
