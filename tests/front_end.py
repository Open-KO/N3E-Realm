"""Spec 11 acceptance 1 and 2 (make test): the front-end cook's bounds on
original synthetic UIF fixtures, and the client loader (build/client/
n3e-front-end-check) on a synthetic front-end.bin and its malformed variants.
No reference assets: the UIF trees, the texture and the font atlas are written
here, and both scenes use the demo package's own N3S1 character. The music
(RQ-018) is synthetic MPEG-1 Layer III frames written bit by bit here: a
96-byte mono frame at 48 kHz whose two granules each carry one count1
quadruple, so it decodes to a quiet low tone (tests/audio.cpp decodes it).
The PCM music (RQ-083) is a synthetic WAV written here with the wave module."""
import io
import json
import math
import re
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile
import wave

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/assetc"))
from common import f, string, u  # noqa: E402
import ko_create  # noqa: E402
import ko_front_end as fe  # noqa: E402

# --- synthetic MPEG audio (RQ-018) ----------------------------------------------


def mp3_frame(tone=True, layer=1, rate=1, padding=0):
    """One MPEG-1 frame, 32 kbit/s, mono, no CRC (96 bytes at 48 kHz, rate
    index 1). `layer` is the header's field (1 is Layer III)."""
    bits = []

    def put(value, n):
        bits.extend((value >> i) & 1 for i in range(n - 1, -1, -1))
    for value, n in ((0x7FF, 11), (3, 2), (layer, 2), (1, 1), (1, 4), (rate, 2), (padding, 1), (0, 1), (3, 2),
                     (0, 2), (0, 1), (0, 1), (0, 2)):
        put(value, n)
    put(0, 9), put(0, 5), put(0, 4)  # main_data_begin, private bits, scfsi
    for _ in range(2):  # granules: count1 only (table B), global gain 210
        for value, n in ((5 if tone else 0, 12), (0, 9), (210, 8), (0, 4), (0, 1), (0, 15), (0, 4), (0, 3),
                         (0, 1), (0, 1), (1, 1)):
            put(value, n)
    for _ in range(2):
        if tone:
            put(0b0111, 4), put(0, 1)  # the quadruple (1, 0, 0, 0), sign +
    size = fe.mpeg_frame(bytes([0xFF, 0xFB, (1 << 4) | (rate << 2) | (padding << 1), 0xC0]), 0, 4)[0]
    bits.extend([0] * (size * 8 - len(bits)))
    return bytes(int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8))


FRAME = mp3_frame()
assert len(FRAME) == 96 and fe.mpeg_frame(FRAME, 0, 96) == (96, 48000, 1, True)
TRACK = FRAME * 10
id3v2 = b"ID3\x03\x00\x00" + bytes([0, 0, 0, 20]) + bytes(20)
assert fe.music_track(TRACK) == (48000, 1, 10, TRACK, 0)
assert fe.music_track(id3v2 + TRACK + b"TAG" + bytes(125)) == (48000, 1, 10, TRACK, 30 + 128)
# KO's intro track ends inside its last frame: that frame is dropped.
assert fe.music_track(TRACK + FRAME[:40]) == (48000, 1, 10, TRACK, 40)
music_problems = {
    "no frames": b"",
    "junk before the frames": b"\0" + TRACK,
    "junk between frames": TRACK[:96] + b"\0" * 4 + TRACK[96:],
    "Layer II": mp3_frame(layer=2) + TRACK,
    "a second sample rate": TRACK + mp3_frame(rate=0),
    "only a cut frame": FRAME[:40],
    "past the track bound": FRAME * (fe.MAX_TRACK_BYTES // 96 + 1),
}
for reason, data in music_problems.items():
    try:
        fe.music_track(data)
    except ValueError:
        continue
    raise AssertionError("music cook accepted " + reason)




def wav(frames, rate=22050, channels=2, width=2, comptype="NONE"):
    """A synthetic WAV: sample i of channel c is (i * 7 + c * 3) % 251 - 125,
    scaled to the width (unsigned for 8-bit, as WAV is)."""
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        raw = bytearray()
        for i in range(frames):
            for c in range(channels):
                v = (i * 7 + c * 3) % 251 - 125
                raw += (v + 128).to_bytes(1, "little") if width == 1 else \
                    (v << (width * 8 - 8)).to_bytes(width, "little", signed=True)
        w.writeframes(bytes(raw))
    data = out.getvalue()
    if comptype != "NONE":  # the format tag at byte 20 (1 is PCM)
        data = data[:20] + struct.pack("<H", 3) + data[22:]
    return data


WAV = wav(100)
PCM = b"".join(struct.pack("<h", ((i * 7 + c * 3) % 251 - 125) << 8) for i in range(100) for c in range(2))
assert fe.pcm_track(WAV) == (22050, 2, 100, PCM, 2)
# Other widths become 16-bit as ko_audio's samples do: 8-bit (v + 128) and
# 24-bit (v << 16) give v << 8.
assert fe.pcm_track(wav(100, width=1)) == (22050, 2, 100, PCM, 1)
assert fe.pcm_track(wav(100, width=3)) == (22050, 2, 100, PCM, 3)
assert fe.pcm_track(wav(10, rate=8000, channels=1))[:3] == (8000, 1, 10)
# RQ-104: a sound (the select turn's, ko_audio.pcm) plays at its own rate: the
# 22,050 Hz 8-bit mono of Snd/char_select_turn.wav (13,961 frames, 0.633 s)
# becomes ceil(13961 x 48000 / 22050) = 30,392 frames of the mixer's 48 kHz,
# the source's length; the music keeps its rate and resamples as it plays
# (tests/audio.cpp pins that length).
import ko_audio  # noqa: E402
assert len(ko_audio.pcm(wav(13961, channels=1, width=1))) // 2 == 30392 == math.ceil(13961 * 48000 / 22050)
assert len(ko_audio.pcm(wav(4410, channels=2))) // 2 == 9600
pcm_problems = {
    "not a WAV": b"RIFF\0\0\0\0WAVEjunk",
    "a float format": wav(10, comptype="float"),
    "a rate below 8 kHz": wav(10, rate=7999),
    "a rate above 96 kHz": wav(10, rate=96001),
    "no frames": wav(0),
    "truncated samples": WAV[:-1],
}
for reason, data in pcm_problems.items():
    try:
        fe.pcm_track(data)
    except ValueError:
        continue
    raise AssertionError("music cook accepted a WAV with " + reason)
# The bound counts the cooked 16-bit bytes, not the file's.
saved = fe.MAX_TRACK_BYTES
fe.MAX_TRACK_BYTES = 399
try:
    fe.pcm_track(WAV)
    raise AssertionError("music cook accepted a PCM track past its bound")
except ValueError:
    pass
finally:
    fe.MAX_TRACK_BYTES = saved


class Tracks:
    def get(self, path):
        return WAV if path.endswith(".wav") else TRACK


one = {"tracks": [{"path": "a.mp3", "loop": True}], "screens": {"login": 0, "select": 0}}
section, played = fe.music(Tracks(), one)
assert section == (u(1) + u(fe.MPEG) + u(48000) + u(1) + u(1) + f([0]) + u(10) + u(len(TRACK)) + TRACK + u(0) + u(0)
                   + u(fe.NO_MUSIC) * 2)
assert played == [dict(path="a.mp3", kind="mpeg", rate=48000, channels=1, frames=10, bytes=960, dropped=0, loop=True,
                       restart=0)], played
assert fe.music(Tracks(), None)[0] == u(0) + u(fe.NO_MUSIC) * 4
# RQ-083: a WAV is a PCM track; a restart period is carried as a real.
two = {"tracks": [{"path": "a.wav", "loop": False, "restart": 21.66}, {"path": "b.wav", "loop": True}],
       "screens": {"login": 0, "select": 1, "create": 1}}
section, played = fe.music(Tracks(), two)
pcm = u(fe.PCM) + u(22050) + u(2)
assert section == (u(2) + pcm + u(0) + f([21.66]) + u(100) + u(400) + PCM + pcm + u(1) + f([0]) + u(100) + u(400) + PCM
                   + u(0) + u(1) + u(1) + u(fe.NO_MUSIC)), section[:80]
assert [(t["kind"], t["loop"], t["restart"], t["width"]) for t in played] == [("pcm", False, 21.66, 2),
                                                                             ("pcm", True, 0, 2)], played
config_problems = {
    "an unknown screen": dict(one, screens={"message": 0}),
    "a screen past the tracks": dict(one, screens={"login": 1}),
    "a loop that is not a flag": dict(one, tracks=[{"path": "a.mp3", "loop": 1}]),
    "five tracks": dict(one, tracks=[{"path": "a.mp3", "loop": True}] * 5),
    "an unknown track key": dict(one, tracks=[{"path": "a.mp3", "loop": True, "loops": 2}]),
    "a restart below 0.1 s": dict(one, tracks=[{"path": "a.mp3", "loop": True, "restart": 0.05}]),
    "a restart past an hour": dict(one, tracks=[{"path": "a.mp3", "loop": True, "restart": 3601}]),
    "a negative restart": dict(one, tracks=[{"path": "a.mp3", "loop": True, "restart": -1}]),
    "a restart that is a flag": dict(one, tracks=[{"path": "a.mp3", "loop": True, "restart": True}]),
    "a restart that is text": dict(one, tracks=[{"path": "a.mp3", "loop": True, "restart": "21.66"}]),
}
for reason, config in config_problems.items():
    try:
        fe.music(Tracks(), config)
    except ValueError:
        continue
    raise AssertionError("music cook accepted " + reason)
print("PASS front-end music cook: frames, tags and a cut last frame, WAVs as PCM, restart periods; %d refusals"
      % (len(music_problems) + len(pcm_problems) + 1 + len(config_problems)))

# --- synthetic UIF (ko_hud.parse's layout) ------------------------------------


def node(kind, ident="", children=(), rect=(0, 0, 32, 16), reserved=0, text="", texture="synthetic.dxt"):
    data = string("") + struct.pack("<hh", len(children), 1)
    data += b"".join(u(k) + v for k, v in children)
    data += string(ident) + struct.pack("<8i2I", *rect, 0, 0, 0, 0, 0, reserved) + string("") * 3
    if kind == 4:
        data += string(texture) + f([0, 0, 1, 1, 0])
    elif kind == 6:
        data += string("Arial") + struct.pack("<2I", 12, 0) + u(0xFFFFFFFF) + string(text) + u(0)
    elif kind == 1:
        data += struct.pack("<4i", *rect) + string("") * 2
    elif kind == 8:
        data += string("") * 2
    elif kind == 9:
        data += u(0)
    elif kind == 14:
        data += string("Arial") + struct.pack("<4I", 12, 0xFFFFFFFF, 0, 0)
    return kind, data


def button(ident):
    # The four state images (reserved 0-3) and a label.
    return node(1, ident, [node(4, reserved=s) for s in range(4)] + [node(6, text=ident)])


def text(ident):
    return node(6, ident, text=ident)


TREES = {
    "login": lambda: node(0, "root", [
        node(0, "Group_LogIn", [button("Btn_Login"), button("Btn_Cancel"), text("notice")]),
        node(0, "Group_ServerList", [node(14, "List_Server"), button("Btn_Connect")])]),
    "select": lambda: node(0, "root", [button("bt_left"), button("bt_right"), button("bt_back"),
                                       button("bt_exit"), text("text00")]),
    "create": lambda: node(0, "root", [button("btn_create"), button("btn_cancel"),
                                       node(8, "edit_name", [node(4, texture=""), text("")]),
                                       node(9, "area_character"),
                                       text("text_desc")]),
    "loading": lambda: node(0, "root", [node(3, "Progress_Loading", [node(4, reserved=0), node(4, reserved=1)])]),
    "message": lambda: node(0, "root", [text("text_msg"), button("btn_ok")]),
}
BINDINGS = {
    "login": {"Group_LogIn": "login_group", "Group_ServerList": "realm_group", "List_Server": "realm_list",
              "Btn_Connect": "realm_connect", "Btn_Login": "login", "Btn_Cancel": "exit", "notice": "notice"},
    "select": {"text00": "char_info", "bt_left": "select_prev", "bt_right": "select_next", "bt_back": "back",
               "bt_exit": "exit"},
    "create": {"btn_create": "create_confirm", "btn_cancel": "back", "edit_name": "name_field",
               "area_character": "char_view", "text_desc": "class_desc"},
    "loading": {"Progress_Loading": "progress"},
    "message": {"text_msg": "message", "btn_ok": "ok"},
}


class Fixture:
    """The client tree: one UIF per screen and a 4 x 4 A4R4G4B4 texture."""

    def __init__(self, trees):
        self.trees = trees

    def get(self, path):
        if path == "synthetic.dxt":
            return string("") + b"NTF\x03" + struct.pack("<4i", 4, 4, 26, 0) + struct.pack("<16H", *([0xF8C4] * 16))
        return self.trees[path]


def spec(name, **over):
    return {"ui": name + ".uif", "place": "origin", "bindings": dict(BINDINGS[name]), **over}


def cook_screens(trees=None, specs=None):
    trees = trees or {n + ".uif": TREES[n]()[1] for n in fe.SCREENS}
    specs = specs or {n: spec(n) for n in fe.SCREENS}
    assets = Fixture(trees)
    textures, fonts = fe.Textures(assets), {}
    data = [fe.screen(n, specs[n], assets, textures, fonts) for n in fe.SCREENS]
    return data, textures, fonts


def refused(reason, **kw):
    try:
        cook_screens(**kw)
    except (ValueError, KeyError, struct.error) as error:
        return str(error)
    raise AssertionError("cook accepted " + reason)


screens, textures, fonts = cook_screens()
counts = [struct.unpack_from("<I", s)[0] for s in screens]
# A button is itself, four state images and its label; an edit omits its string.
assert counts == [23, 26, 16, 4, 8], counts
assert len(textures.list) == 1 and len(fonts) == 1, (textures.list, fonts)

trees = {n + ".uif": TREES[n]()[1] for n in fe.SCREENS}
problems = {
    "truncated UIF": dict(trees={**trees, "login.uif": trees["login.uif"][:-5]}),
    "trailing UIF bytes": dict(trees={**trees, "login.uif": trees["login.uif"] + b"\0"}),
    "unknown action": dict(specs={**{n: spec(n) for n in fe.SCREENS},
                                  "login": spec("login", bindings={**BINDINGS["login"], "Btn_Login": "teleport"})}),
    "unbound required action": dict(specs={**{n: spec(n) for n in fe.SCREENS},
                                           "select": spec("select", hidden=["bt_back"])}),
    "missing bound node": dict(specs={**{n: spec(n) for n in fe.SCREENS},
                                      "message": spec("message", bindings={**BINDINGS["message"], "btn_no": "back"})}),
    "action bound twice": dict(specs={**{n: spec(n) for n in fe.SCREENS},
                                      "select": spec("select", bindings={**BINDINGS["select"], "bt_left": "exit"})}),
    # RQ-108 (version 12): login_closed is the login screen's only.
    "login_closed off the login": dict(
        trees={**trees, "select.uif": node(0, "root", [button("bt_left"), button("bt_right"), button("bt_back"),
                                                       button("bt_exit"), text("text00"), text("rights")])[1]},
        specs={**{n: spec(n) for n in fe.SCREENS},
               "select": spec("select", bindings={**BINDINGS["select"], "rights": "login_closed"})}),
    # RQ-109 (version 13): a select binds an info text (char_info or any of
    # 1298's three), and 1298's bar actions are the select's only.
    "select without an info text": dict(specs={**{n: spec(n) for n in fe.SCREENS},
                                               "select": spec("select", hidden=["text00"])}),
    "select bar action off the select": dict(specs={**{n: spec(n) for n in fe.SCREENS},
                                                    "login": spec("login", bindings={**BINDINGS["login"],
                                                                                     "notice": "char_name"})}),
    # RQ-111 (version 14): yes and no are the message box's only.
    "yes off the message box": dict(specs={**{n: spec(n) for n in fe.SCREENS},
                                           "login": spec("login", bindings={**BINDINGS["login"], "notice": "yes"})}),
    # RQ-130 (version 21): the race and class choices are create's only, each
    # a button with no fixed state.
    "create choice off create": dict(specs={**{n: spec(n) for n in fe.SCREENS},
                                            "login": spec("login", bindings={**BINDINGS["login"],
                                                                             "notice": "create_race"})}),
    "create choice on a text": dict(specs={**{n: spec(n) for n in fe.SCREENS},
                                           "create": spec("create", bindings={**BINDINGS["create"],
                                                                              "text_desc": "create_class"})}),
    "edit with two strings": dict(trees={**trees, "create.uif": node(0, "root", [
        button("btn_create"), button("btn_cancel"), node(8, "edit_name", [text(""), text("")]),
        node(9, "area_character")])[1]}),
    "UIF tree over its bound": dict(trees={**trees, "loading.uif": node(0, "root", [
        node(0, "g%d" % i, [node(0) for _ in range(40)]) for i in range(52)] + [
        node(3, "Progress_Loading")])[1]}),
    "screen nodes over the front-end bound": dict(trees={**trees, "loading.uif": node(0, "root", [
        node(0, "g%d" % i, [node(0) for _ in range(30)]) for i in range(34)] + [
        node(3, "Progress_Loading")])[1]}),
}
for reason, kw in problems.items():
    refused(reason, **kw)
try:
    fe.write(Fixture(trees), pathlib.Path("/nonexistent"), {"screens": {n: spec(n) for n in fe.SCREENS[:-1]}},
             pathlib.Path("/nonexistent"))
    raise AssertionError("cook accepted a missing screen")
except ValueError as error:
    assert str(error) == "front-end screens", error
print("PASS front-end cook: five synthetic screens, %d refusals and a missing screen" % len(problems))

# RQ-109 (version 13, KO-FINDINGS 9.6): 1298's select bar, its start, create
# and delete buttons and its three info texts in place of char_info.
BAR_BINDINGS = {"btn_start": "select_start", "btn_create": "select_create", "btn_delete": "select_delete",
                "btn_back": "back", "btn_exit": "exit", "btn_left": "select_prev", "btn_right": "select_next",
                "str_id": "char_name", "str_lev": "char_level", "str_job": "char_class"}


def bar_tree(info=("str_id", "str_lev", "str_job")):
    return node(0, "root", [button(b) for b in ("btn_create", "btn_start", "btn_delete", "btn_back", "btn_exit",
                                                "btn_left", "btn_right")] + [text(t) for t in info])[1]


def bar(info=("str_id", "str_lev", "str_job")):
    """The synthetic screens with a 1298 bar for the select."""
    bindings = {k: v for k, v in BAR_BINDINGS.items() if not k.startswith("str_") or k in info}
    return cook_screens(trees={**trees, "select.uif": bar_tree(info)},
                        specs={**{n: spec(n) for n in fe.SCREENS}, "select": spec("select", bindings=bindings)})[0]


bar_screens = bar()
assert struct.unpack_from("<I", bar_screens[1])[0] == 1 + 7 * 6 + 3, struct.unpack_from("<I", bar_screens[1])
for info in (("str_id",), ("str_lev",), ("str_job",)):
    bar(info)
print("PASS front-end cook: 1298's select bar, its info texts in place of char_info")

# RQ-130 (version 21, KO-FINDINGS 9.15): 1298's create's race and class
# buttons (00604f90). RQ-172 (version 25): every race and class button bound by
# the create screen's `races` (KO's race code and the race's default class,
# 1298's 005fd120) and `classes` (the specialty codes it stands for, the image
# drawn in its place while the race cannot take it, 1298's 006060f0, and the
# stat labels its click marks, 006062d0), cooked as create's choice section
# (item 14); `class_labels` says whether a mark hides them (1298) or shows
# them (1264, 0043ee10).
CHOICE_RACES = {"btn_race_ka_tu": {"race": 2, "default": 102}}
CHOICE_CLASSES = {"btn_class_warrior": {"specialties": [101, 201], "image": "img_warrior", "labels": ["str_01"]},
                  "btn_class_priest": {"specialties": [104, 204], "image": "img_priest",
                                       "labels": ["str_01", "int_01"]}}


def choice_tree():
    return node(0, "root", [button("btn_create"), button("btn_cancel"),
                            node(8, "edit_name", [node(4, texture=""), text("")]), node(9, "area_character"),
                            text("text_desc"), node(4, "img_warrior"), node(4, "img_priest"),
                            node(4, "img_blank", texture=""), text("str_02"), text("str_01"), text("int_01"),
                            button("btn_race_ka_tu"), button("btn_race_ka_wt"), button("btn_class_warrior"),
                            button("btn_class_priest")])[1]


def choice_cook(specs=None, **create):
    spec_create = {"races": CHOICE_RACES, "classes": CHOICE_CLASSES, "class_labels": "hide", **create}
    spec_create = {k: v for k, v in spec_create.items() if v is not None}  # None: left out
    assets = Fixture({**trees, "create.uif": choice_tree()})
    textures, fonts, choices = fe.Textures(assets), {}, []
    specs = {**{n: spec(n) for n in fe.SCREENS}, "create": spec("create", **spec_create), **(specs or {})}
    data = [fe.screen(n, specs[n], assets, textures, fonts, choices=choices) for n in fe.SCREENS]
    return data, choices[0]


def choice_screens(**create):
    return choice_cook(**create)[0]


def node_records(data):
    """Each cooked node's (id, action, flags), in order."""
    out, at = [], 4
    for _ in range(struct.unpack_from("<I", data)[0]):
        length = struct.unpack_from("<I", data, at + 24)[0]
        ident = data[at + 28:at + 28 + length].decode()
        action, flags = struct.unpack_from("<2I", data, at + 28 + length)
        out.append((ident, action, flags))
        at = fe.node_end(data, at)
    return out


def choice_section(data):
    """Create's choice section (item 14): ([(node, race, default)], [(node,
    specialties, image, labels)])."""
    words = list(struct.unpack("<%dI" % (len(data) // 4), data))
    races = [tuple(words[1 + 3 * i:4 + 3 * i]) for i in range(words[0])]
    at, classes = 2 + 3 * words[0], []
    for _ in range(words[at - 1]):
        node_index, count = words[at], words[at + 1]
        codes, image, labels = words[at + 2:at + 2 + count], words[at + 2 + count], words[at + 3 + count]
        classes.append((node_index, codes, image, words[at + 4 + count:at + 4 + count + labels]))
        at += 4 + count + labels
    assert at == len(words), (at, words)
    return races, classes


CHOICE, CHOSEN = choice_cook()
records = node_records(CHOICE[2])
index = {i: k for k, (i, _, _) in enumerate(records)}
chosen = {i: (a, f) for i, a, f in records if i.startswith(("btn_race", "btn_class", "str_", "int_"))}
assert chosen == {"btn_race_ka_tu": (fe.ACTIONS.index("create_race"), 0), "btn_race_ka_wt": (0, 0),
                  "btn_class_warrior": (fe.ACTIONS.index("create_class"), 0),
                  "btn_class_priest": (fe.ACTIONS.index("create_class"), 0),
                  "str_02": (0, 0), "str_01": (0, fe.CLASS_HIDES), "int_01": (0, fe.CLASS_HIDES)}, chosen
assert choice_section(CHOSEN["data"]) == (
    [(index["btn_race_ka_tu"], 2, 102)],
    [(index["btn_class_warrior"], [101, 201], index["img_warrior"], [index["str_01"]]),
     (index["btn_class_priest"], [104, 204], index["img_priest"], [index["str_01"], index["int_01"]])]), \
    choice_section(CHOSEN["data"])
assert CHOSEN["races"] == [(2, 102)] and CHOSEN["classes"] == [[101, 201], [104, 204]], CHOSEN
shown = {i: f for i, _, f in node_records(choice_screens(class_labels="show")[2])}
assert shown["str_01"] == shown["int_01"] == fe.CLASS_SHOWS and shown["str_02"] == 0, shown
assert fe.CLASS_HIDES == 16 and fe.CLASS_SHOWS == 32 and fe.ACTIONS[-2:] == ("create_race", "create_class") and \
    fe.ONLY_ON["create_race"] == "create", fe.ACTIONS
# A race or class button `down` is chosen at each open (the 1097 choice's):
# fixed on, every state image kept (the client draws it down while chosen).
for button_id in ("btn_race_ka_tu", "btn_class_priest"):
    data = choice_screens(states={button_id: "down"})[2]
    flags = {i: f for i, _, f in node_records(data)}
    assert flags[button_id] == fe.FIXED_ON, flags
    for state in ("on", "disabled"):
        try:
            choice_screens(states={button_id: state})
        except ValueError as error:
            assert "a button with no fixed state but down" in str(error), error
            continue
        raise AssertionError(("cooked a create choice with a fixed state", button_id, state))
choice_problems = (
    ("create's only", dict(specs={"login": spec("login", races={"notice": {"race": 2, "default": 102}})})),
    ("bound by the create screen's races and classes",
     dict(bindings={**BINDINGS["create"], "btn_race_ka_wt": "create_race"})),
    ("bound, hidden or named twice", dict(hidden=["btn_race_ka_tu"])),
    ("bound, hidden or named twice", dict(bindings={**BINDINGS["create"], "btn_class_priest": "info"})),
    ("exactly {race, default}", dict(races={"btn_race_ka_tu": {"race": 2}})),
    ("1 to 16 distinct ids", dict(races={"btn_race_ka_tu": {"race": 0, "default": 102}})),
    ("1 to 16 distinct ids", dict(classes={"btn_class_priest": {"specialties": []}})),
    ("1 to 16 distinct ids", dict(classes={"btn_class_priest": {"specialties": [104, 104]}})),
    ("race 2 twice", dict(races={**CHOICE_RACES, "btn_race_ka_wt": {"race": 2, "default": 102}})),
    ("a specialty in two class buttons",
     dict(classes={**CHOICE_CLASSES, "btn_class_warrior": {"specialties": [101, 204]}})),
    ("image: an image, not hidden, one class's",
     dict(classes={"btn_class_priest": {"specialties": [104], "image": "text_desc"}})),
    ("image: an image, not hidden, one class's", dict(hidden=["img_priest"])),
    ("image: an image, not hidden, one class's",
     dict(classes={**CHOICE_CLASSES, "btn_class_warrior": {"specialties": [101], "image": "img_priest"}})),
    ("labels: a node named twice or hidden",
     dict(classes={"btn_class_priest": {"specialties": [104], "labels": ["str_01", "str_01"]}})),
    ("labels: a node named twice or hidden", dict(hidden=["int_01"])),
    ("labels need the create screen's class_labels", dict(class_labels=None)),
    ("class_labels: one of", dict(class_labels="flash")),
    ("class_labels: no class names labels",
     dict(classes={"btn_class_priest": {"specialties": [104], "image": "img_priest"}})),
    ("a race or class button or a class image",
     dict(classes={**CHOICE_CLASSES, "btn_class_warrior": {"specialties": [101], "labels": ["img_priest"]}})),
    ("a node they name is not drawn",
     dict(classes={**CHOICE_CLASSES, "btn_class_warrior": {"specialties": [101], "image": "img_blank"}})),
    ("more than one down", dict(states={"btn_class_priest": "down", "btn_class_warrior": "down"})),
    ("until_race: gone in version 25", dict(until_race=["img_priest"])),
    ("until_class: gone in version 25", dict(until_class=["str_01"])))
for reason, kw in choice_problems:
    try:
        choice_cook(**kw)
    except ValueError as error:
        assert reason in str(error), (reason, error)
        continue
    raise AssertionError(("cooked create choices", reason, kw))
# With the package's rules (character-create.json): each race button a race of
# the package and its default one of that race's specialties; each class only
# specialties some race has, a race taking at most one of a class's.
moradon_rules = ko_create.rules(ROOT / "games/moradon")
fe.create_buttons(CHOSEN, moradon_rules)
fe.create_buttons({"races": [], "classes": []}, None)
for reason, choice in (
        ("race 5 is not one of the package's", {"races": [(5, 102)], "classes": []}),
        ("race 2's default 101 is not one of its specialties", {"races": [(2, 101)], "classes": []}),
        ("specialty 999 is no race's", {"races": [], "classes": [[104, 999]]}),
        ("race 12 takes two specialties of one class button", {"races": [], "classes": [[201, 202]]}),
        ("the package has no create rules", None)):
    try:
        fe.create_buttons(choice or CHOSEN, None if choice is None else moradon_rules)
    except ValueError as error:
        assert reason in str(error), (reason, error)
        continue
    raise AssertionError(("accepted create buttons", reason))
# Both recipes bind KO's codes (binary): 1298's 006062d0 maps its four class
# buttons to 101/201 .. 104/204 and hides each clicked class's two cream
# labels, by Load's 00603850 order str_01, dex_01, sta_01, int_01, map_01:
# warrior 0 and 2, rogue 1 and 2, mage 3 and 4, priest 0 and 3; 1264's
# 0043ee10 shows the same pairs of pink img_* labels; each race button's
# default is 005fd120's (the Tuarek's 102). Only the Tuarek, the race create
# offers (Q105), is bound; the others keep their states (Q109 (a)). Moradon
# offers the Tuarek's rogue and priest, so both buttons are live.
create_1298 = json.loads((ROOT / "games/moradon/front-end-1298.json").read_text())["screens"]["create"]
create_1097 = json.loads((ROOT / "games/moradon/front-end.json").read_text())
PAIRS = {"warrior": ("str", "sta"), "rogue": ("dex", "sta"), "mage": ("int", "map"), "priest": ("str", "int")}
CODES = {"warrior": [101, 201], "rogue": [102, 202], "mage": [103, 203], "priest": [104, 204]}
for recipe, label, mode in ((create_1298, "%s_01", "hide"), (create_1097["screens"]["create"], "img_%s", "show")):
    assert recipe["races"] == {"btn_race_ka_tu": {"race": 2, "default": 102}}, recipe["races"]
    assert {k: {**v, "labels": sorted(v["labels"])} for k, v in recipe["classes"].items()} == {
        "btn_class_" + c: {"specialties": CODES[c], "image": "img_" + c,
                           "labels": sorted(label % x for x in PAIRS[c])} for c in CODES}, recipe["classes"]
    assert recipe["class_labels"] == mode and "until_race" not in recipe and "until_class" not in recipe, recipe
    assert not {"create_race", "create_class"} & set(recipe["bindings"].values()), recipe["bindings"]
    assert not {"btn_class_" + c for c in CODES} & {k for k, v in recipe["states"].items() if v != "down"}, recipe
    assert recipe["states"]["btn_race_ka_at"] == recipe["states"]["btn_race_ka_wt"] == "disabled", recipe["states"]
    fe.create_buttons({"races": [(v["race"], v["default"]) for v in recipe["races"].values()],
                       "classes": [v["specialties"] for v in recipe["classes"].values()]}, moradon_rules)
# The 1298 recipe waits for both (no button down) and words the two refusals
# with 1298's rows (00600750: code 7 row 1908, code 9 row 1904, each under row
# 1901); its Puri Tuarek stays disabled (its layout's disabled tile).
assert "down" not in create_1298["states"].values() and create_1298["states"]["btn_race_ka_pt"] == "disabled"
messages_1298 = json.loads((ROOT / "games/moradon/front-end-1298.json").read_text())["messages"]
assert messages_1298["create_no_race"] == {"title": {"table": "Data/Texts_us.tbl", "row": 1901},
                                           "text": {"table": "Data/Texts_us.tbl", "row": 1908}}, messages_1298
assert messages_1298["create_no_class"] == {"title": {"table": "Data/Texts_us.tbl", "row": 1901},
                                            "text": {"table": "Data/Texts_us.tbl", "row": 1904}}, messages_1298
# The 1097 choice: its Tuarek and priest chosen at each open (Q52, Q89 (b));
# a Tuarek click unchooses the priest as 1264's 0043ec90 does, so Create may
# say 1264's row 1904 under 1901 (0043a340, 0043a820); a race is never
# unchosen, so it words no create_no_race.
assert create_1097["messages"]["create_no_class"] == {
    "title": {"table": "installer-1264:Data/Texts_us.tbl", "row": 1901},
    "text": {"table": "installer-1264:Data/Texts_us.tbl", "row": 1904}}, create_1097["messages"]
assert "create_no_race" not in create_1097["messages"], create_1097["messages"]
print("PASS front-end cook: create's race and class buttons by KO's codes, each class's image and labels, %d "
      "refusals; both recipes bind the Tuarek and the four classes as 1298 and 1264 map them, the 1298 recipe "
      "waiting for both, the 1097 choice choosing the Tuarek and the priest at each open" % len(choice_problems))

# RQ-138 (Q89 (b), KO-FINDINGS 9.16): the recipe state `down`, 1264's chosen
# race and class (0043ec90 and 0043ee10 set state 3, which Render 00403a70
# draws with BS_DOWN): fixed on in the file, the button's down image (state
# image 1) drawn in the down and on states and its on image (2) not written.
def masks(data):
    """Each cooked node's (kind, id, parent, flags, mask), in order."""
    out, at = [], 4
    for _ in range(struct.unpack_from("<I", data)[0]):
        kind, parent = struct.unpack_from("<2I", data, at)
        length = struct.unpack_from("<I", data, at + 24)[0]
        ident = data[at + 28:at + 28 + length].decode()
        _action, flags, mask = struct.unpack_from("<3I", data, at + 28 + length)
        out.append((kind, ident, parent, flags, mask))
        at = fe.node_end(data, at)
    return out


def fixed_tree(chosen):
    return node(0, "root", [button("btn_create"), button("btn_cancel"),
                            node(8, "edit_name", [node(4, texture=""), text("")]), node(9, "area_character"),
                            text("text_desc"), chosen])[1]


def fixed_screens(chosen=None, **create):
    tree = fixed_tree(chosen or button("btn_race_ka_tu"))
    return cook_screens(trees={**trees, "create.uif": tree},
                        specs={**{n: spec(n) for n in fe.SCREENS}, "create": spec("create", **create)})[0]


def fixed_images(state):
    records = masks(fixed_screens(states={"btn_race_ka_tu": state})[2])
    at = next(i for i, r in enumerate(records) if r[1] == "btn_race_ka_tu")
    return records[at][3], [m for kind, _, parent, _flags, m in records
                            if parent == at and kind == fe.KINDS["image"]]


assert fixed_images("on") == (fe.FIXED_ON, [1, 2, 4, 8]), fixed_images("on")
assert fixed_images("down") == (fe.FIXED_ON, [1, 2 | 4, 8]), fixed_images("down")
for reason, chosen in (
        ("a button with no down image", text("btn_race_ka_tu")),
        ("a button with no down image",
         node(1, "btn_race_ka_tu", [node(4, reserved=s, texture="" if s == 1 else "synthetic.dxt") for s in range(4)])),
        ("a button with no down image", node(1, "btn_race_ka_tu", [node(4, reserved=s) for s in (0, 2, 3)]))):
    try:
        fixed_screens(chosen, states={"btn_race_ka_tu": "down"})
    except ValueError as error:
        assert "state down: " + reason in str(error), (reason, error)
        continue
    raise AssertionError(("cooked state down", reason))
# The 1097 choice: its Tuarek and priest are chosen at each open (Q52) and
# draw down, as 1264's chosen buttons; no button is fixed on.
states_1097 = create_1097["screens"]["create"]["states"]
assert states_1097["btn_race_ka_tu"] == "down" and states_1097["btn_class_priest"] == "down", states_1097
assert "on" not in states_1097.values(), states_1097
# RQ-139 (KO-FINDINGS 9.16, the maintainer's "Grey button, as 1264"): the Puri
# Tuarek's disabled image has no texture, so it takes no fixed state and no
# action: it draws its normal tile, as 1264's race buttons at rest (0043ec90
# sets them 2), and takes no pointer, as the fixed disabled Arch and Wrinkle
# Tuarek, whose disabled image is their normal tile (Q109 (a)).
assert "btn_race_ka_pt" not in states_1097, states_1097
assert "btn_race_ka_pt" not in create_1097["screens"]["create"]["bindings"], create_1097["screens"]["create"]
assert "btn_race_ka_pt" not in create_1097["screens"]["create"]["races"], create_1097["screens"]["create"]
# RQ-142 (Q91 (b)) and RQ-172: after a Tuarek and a priest click 1264 hides the
# warrior and mage buttons for img_warrior and img_mage and hides img_rogue
# and img_priest (0043ec90(2), 0043ee10(104)); the client draws that column
# from the class buttons' codes and images (the Tuarek takes the rogue and the
# priest), so the recipe hides none of them, and the rogue is live.
# RQ-144 (Q92 (b)): the priest's mark shows img_str and img_int (0043ee10(104)),
# pink copies over the light "Strength" and "Intelligence"; the other three
# are the other classes' labels, shown when they are marked. The stat values
# stay empty and text_bonus hidden.
assert create_1097["screens"]["create"]["hidden"] == ["text_bonus"], create_1097["screens"]["create"]["hidden"]
assert "btn_class_rogue" not in states_1097, states_1097
print("PASS front-end cook: the recipe state down, the down image in the on state, the 1097 choice's Tuarek and "
      "priest chosen at each open, its Puri Tuarek unfixed and unbound, its class column and pink labels drawn "
      "by the class buttons' codes")


# RQ-084: a layout from another input (`<name>:<path>`) reads its textures from
# that input's tree; an unprefixed one from the first.
class Other(Fixture):
    def get(self, path):
        if path == "synthetic.dxt":
            return string("") + b"NTF\x03" + struct.pack("<4i", 8, 8, 26, 0) + struct.pack("<64H", *([0x8F4C] * 64))
        return self.trees[path]


both = fe.Inputs([Fixture(trees), Other({"login.uif": trees["login.uif"]})], [None, "other"])
textures, fonts = fe.Textures(both), {}
data = [fe.screen(n, spec(n, ui=("other:" if n == "login" else "") + n + ".uif"), both, textures, fonts)
        for n in fe.SCREENS]
assert [(w, h) for w, h, _ in textures.list] == [(8, 8), (4, 4)], [(w, h) for w, h, _ in textures.list]
assert data[0] == screens[0] and [struct.unpack_from("<I", d)[0] for d in data] == counts
try:
    fe.screen("login", spec("login", ui="third:login.uif"), both, fe.Textures(both), {})
    raise AssertionError("cook read a layout from an input the choice lacks")
except ValueError as error:
    assert "no input named 'third'" in str(error), error
print("PASS front-end cook: a layout and its textures from a second input tree")

# --- the loader ----------------------------------------------------------------

# RQ-067: the select camera's turn ends where 1097's check ends it
# (0043dc50, 0043dfb0: the eye turned a further 0.01 rad has a cosine below the
# slot's `turn_end` with the camera's own eye, both from `at`). A synthetic
# camera with a height offset, so the check's cosine is not the angle's.
TURN_CAMERA = {"eye": [0.5, 1.0, 6.0], "at": [0.5, -0.5, 0.0]}


def ko_turn_ends(camera, angle, end):
    """KO's CheckRotateLeft/Right on an eye turned by `angle` (RotationY, KO
    space) from the camera's own: True once the turn has ended."""
    (ex, ey, ez), (ax, ay, az) = camera["eye"], camera["at"]
    o = [ex - ax, ey - ay, ez - az]
    b = angle + math.copysign(fe.TURN_CHECK_STEP, angle)
    t = [o[0] * math.cos(b) + o[2] * math.sin(b), o[1], -o[0] * math.sin(b) + o[2] * math.cos(b)]
    return sum(o[i] * t[i] for i in range(3)) / sum(v * v for v in o) < end


assert fe.turn_end_eye(TURN_CAMERA, {"position": [0.5, 0, 3]}, 0) == TURN_CAMERA["eye"]
for side, end in ((1, 0.75), (-1, 0.77)):
    eye = fe.turn_end_eye(TURN_CAMERA, {"position": [0.5 + side * 2, 0, 2], "turn_end": end}, 1)
    ax, az = TURN_CAMERA["at"][0], TURN_CAMERA["at"][2]
    o = [TURN_CAMERA["eye"][0] - ax, TURN_CAMERA["eye"][2] - az]
    angle = math.atan2(o[1] * (eye[0] - ax) - o[0] * (eye[2] - az), o[0] * (eye[0] - ax) + o[1] * (eye[2] - az))
    assert eye[1] == TURN_CAMERA["eye"][1] and side * angle > 0, (eye, angle)
    # Up to the cooked angle the turn goes on; any step past it ends it.
    assert not ko_turn_ends(TURN_CAMERA, angle * (1 - 1e-6), end), (side, angle)
    assert ko_turn_ends(TURN_CAMERA, angle * (1 + 1e-6), end), (side, angle)
for slot, index in (({"position": [0.5, 0, 3], "turn_end": 0.75}, 0), ({"position": [2.5, 0, 2]}, 1),
                    ({"position": [0.5, 0, 2], "turn_end": 0.75}, 1), ({"position": [2.5, 0, 2], "turn_end": 1.5}, 1),
                    ({"position": [2.5, 0, 2], "turn_end": 0.99999}, 1)):
    try:
        fe.turn_end_eye(TURN_CAMERA, slot, index)
    except ValueError:
        continue
    raise AssertionError(("cooked", slot, index))

# RQ-086: select.front_clip names the hall's front-clip mode, `hover` (1097) or
# `loop` (1298), and is refused missing or misspelt, before any KO file is read.
SELECT = {"camera": dict(TURN_CAMERA, fov=0.96, near=0.1, far=100), "spot_theta": 0.5, "spot_phi": 0.6,
          "spot_step": 0.02, "slots": [{"position": [0.5, 0, 3], "yaw": 0, "spot": [0, 2, 7],
                                        "spot_target": [0, 0, 3]}]}
for mode in (None, "Hover", "once", 1):
    config = dict(SELECT) if mode is None else dict(SELECT, front_clip=mode)
    try:
        fe.select_scene(Fixture({}), fe.Textures(Fixture({})), config, pathlib.Path("/nonexistent"))
    except ValueError as error:
        assert str(error) == "front-end select.front_clip: one of hover, loop", error
        continue
    raise AssertionError(("cooked front_clip", mode))
assert fe.FRONT_CLIP == {"hover": 0, "loop": 1}, fe.FRONT_CLIP

# RQ-087: select.turn names the camera's turn mode, `rotate` (1097) or `path`
# (1298), and is refused missing or misspelt, before any KO file is read.
for turn in (None, "Path", "orbit", 0):
    config = dict(SELECT, front_clip="loop") if turn is None else dict(SELECT, front_clip="loop", turn=turn)
    try:
        fe.select_scene(Fixture({}), fe.Textures(Fixture({})), config, pathlib.Path("/nonexistent"))
    except ValueError as error:
        assert str(error) == "front-end select.turn: one of rotate, path", error
        continue
    raise AssertionError(("cooked turn", turn))
assert fe.TURN == {"rotate": 0, "path": 1}, fe.TURN

# RQ-116: select.escape names what ESC presses on the select, `back` (the
# realm's, the default) or `exit` (1264's OnKeyPress 004454e0 presses bt_exit),
# or (RQ-119) `none` (1298's bar OnKeyPress 00607810 presses no button, only
# skipping a playing path), and is refused misspelt, before any KO file is read.
for escape in ("Exit", "quit", "None", "skip", 1, 2, None):
    config = dict(SELECT, front_clip="loop", turn="rotate", escape=escape)
    try:
        fe.select_scene(Fixture({}), fe.Textures(Fixture({})), config, pathlib.Path("/nonexistent"))
    except ValueError as error:
        assert str(error) == "front-end select.escape: one of back, exit, none", error
        continue
    raise AssertionError(("cooked escape", escape))
assert fe.ESCAPE == {"back": 0, "exit": 1, "none": 2}, fe.ESCAPE

# RQ-112: select.back names where the select's Back lands, `login` (the
# realm's, the default) or `realms` (1298's Back sets its login procedure's
# +0x21, whose Init 005f68e0 connects, asks for the server list and hides the
# bar), and is refused misspelt, before any KO file is read.
for back in ("Login", "servers", "server_list", "realm", 0, 1, None):
    config = dict(SELECT, front_clip="loop", turn="rotate", back=back)
    try:
        fe.select_scene(Fixture({}), fe.Textures(Fixture({})), config, pathlib.Path("/nonexistent"))
    except ValueError as error:
        assert str(error) == "front-end select.back: one of login, realms", error
        continue
    raise AssertionError(("cooked back", back))
assert fe.BACK == {"login": 0, "realms": 1}, fe.BACK

# RQ-113: select.arrows names the end-of-row arrow rule, `hide` (the realm's,
# the default) or `draw` (KO's: no code in 1298, 1264 or 1097 hides an arrow,
# specs/KO-FINDINGS.md 9.6, 9.13), and is refused misspelt, before any KO file
# is read.
for arrows in ("Hide", "show", "both", "always", 0, 1, True, None):
    config = dict(SELECT, front_clip="loop", turn="rotate", arrows=arrows)
    try:
        fe.select_scene(Fixture({}), fe.Textures(Fixture({})), config, pathlib.Path("/nonexistent"))
    except ValueError as error:
        assert str(error) == "front-end select.arrows: one of hide, draw", error
        continue
    raise AssertionError(("cooked arrows", arrows))
assert fe.ARROWS == {"hide": 0, "draw": 1}, fe.ARROWS

# RQ-125: select.create names where create draws, `screen` (the realm's, the
# default) or `hall` (1298's: a window of the select over the hall,
# specs/KO-FINDINGS.md 9.15), and is refused misspelt; over the hall every
# slot names the new character's turn there (create_yaw, degrees), and a
# create_yaw without it is refused, all before any KO file is read.
for create in ("Hall", "select", "over", 0, 1, True, None):
    config = dict(SELECT, front_clip="loop", turn="rotate", create=create)
    try:
        fe.select_scene(Fixture({}), fe.Textures(Fixture({})), config, pathlib.Path("/nonexistent"))
    except ValueError as error:
        assert str(error) == "front-end select.create: one of screen, hall", error
        continue
    raise AssertionError(("cooked create", create))
assert fe.CREATE == {"screen": 0, "hall": 1}, fe.CREATE
YAWED = [dict(SELECT["slots"][0], create_yaw=yaw) for yaw in (213,)]
for config, reason in ((dict(SELECT, create="hall"), "degrees, -360 to 360"),
                       (dict(SELECT, create="hall", slots=[dict(YAWED[0], create_yaw=361)]), "degrees, -360 to 360"),
                       (dict(SELECT, create="hall", slots=[dict(YAWED[0], create_yaw="213")]), "degrees, -360 to 360"),
                       (dict(SELECT, create="hall", slots=[dict(YAWED[0], create_yaw=math.inf)]), "degrees, -360 to 360"),
                       (dict(SELECT, slots=YAWED), "only with select.create hall"),
                       (dict(SELECT, create="screen", slots=YAWED), "only with select.create hall")):
    try:
        fe.select_scene(Fixture({}), fe.Textures(Fixture({})), dict(config, front_clip="loop", turn="rotate"),
                        pathlib.Path("/nonexistent"))
    except ValueError as error:
        assert str(error) == "front-end select.slots create_yaw: " + reason, (config, error)
        continue
    raise AssertionError(("cooked create_yaw", config))
# Over the hall the create layout binds no char_view (the new character
# stands in the hall); a screen of its own binds it.
UNVIEWED = dict(required=fe.REQUIRED["create"] - {"char_view"}, refused={"char_view"})
viewless = {k: v for k, v in BINDINGS["create"].items() if v != "char_view"}
hall_create = fe.screen("create", spec("create", bindings=viewless), Fixture(trees), fe.Textures(Fixture(trees)), {},
                        **UNVIEWED)
assert struct.unpack_from("<I", hall_create)[0] == counts[2], hall_create[:4]
for bindings, kw, reason in ((BINDINGS["create"], UNVIEWED, "front-end create: binds ['char_view']"),
                             (viewless, {}, "front-end create: unbound ['char_view']")):
    try:
        fe.screen("create", spec("create", bindings=bindings), Fixture(trees), fe.Textures(Fixture(trees)), {}, **kw)
    except ValueError as error:
        assert str(error) == reason, error
        continue
    raise AssertionError(("cooked create", bindings, kw))
print("PASS front-end cook: where create draws, its new character's turn at each slot, and its char_view")


def n3camera(eye, at, rate=30.0, up_keys=0, at_kind=0, tail=b""):
    """A synthetic .n3camera as CN3Camera::Load reads it (1298: 00439540 after
    0043b480): the name, eye, rotation and up, the eye, rotation (here the at)
    and up key sets, the at, __CameraData (0x16c bytes) and the fog's use and
    colour."""
    def keys(values, kind=0):
        if not values:
            return u(0)
        width = 3 if kind == 0 else 4
        return u(len(values)) + u(kind) + f([rate]) + b"".join(f(list(v)[:width] + [0] * (width - len(v))) for v in values)
    out = string("synthetic_camera") + f(list(eye[0] if eye else [0, 0, 0]) + [0, 0, 0, 1] + [0, 1, 0])
    out += keys(eye) + keys(at, at_kind) + (keys([[0, 1, 0]] * up_keys) if up_keys else u(0))
    return out + f(list(at[0] if at else [0, 0, 0])) + bytes(fe.CAMERA_DATA) + struct.pack("<iI", 1, 0xFFFFFFFF) + tail


EYE = [[1, 2, 3], [4, 5, 6]]
AT = [[0, 0, 10], [0, 1, 10]]
assert fe.camera_path(Fixture({"c.n3camera": n3camera(EYE, AT)}), "c.n3camera") == (30.0, EYE, 30.0, AT)
for reason, data in {"no eye keys": n3camera([], AT), "no at keys": n3camera(EYE, []),
                     "up keys": n3camera(EYE, AT, up_keys=1), "rotation keys for the at": n3camera(EYE, AT, at_kind=1),
                     "trailing bytes": n3camera(EYE, AT, tail=b"\0"), "truncated": n3camera(EYE, AT)[:-1]}.items():
    try:
        fe.camera_path(Fixture({"c.n3camera": data}), "c.n3camera")
    except ValueError:
        continue
    raise AssertionError("cooked a camera path with " + reason)
# The path mode's paths: the entry path into slot 0 and both ways between the
# neighbours; the records (from, to, eye rate and keys, at rate and keys,
# engine space) and each slot's rest eye, the last eye key into it.
CAMERAS = {name: n3camera([[i, 0, 1], [i, 0, 2]], AT) for i, name in enumerate(("e", "01", "02", "10", "20"))}
PATHS = [{"to": 0, "path": "e"}, {"from": 0, "to": 1, "path": "01"}, {"from": 0, "to": 2, "path": "02"},
         {"from": 1, "to": 0, "path": "10"}, {"from": 2, "to": 0, "path": "20"}]
records, rest = fe.turn_paths(Fixture(CAMERAS), {"paths": PATHS}, 3)
assert rest == [[0, 0, 2], [1, 0, 2], [2, 0, 2]], rest
assert records[:4] == u(5) and records[4:12] == u(fe.ENTRY) + u(0), records[:12]
assert records[12:44] == f([30.0]) + u(2) + f([0, 0, -1, 0, 0, -2]), records[12:44]
assert fe.turn_paths(Fixture(CAMERAS), {"paths": PATHS[:1]}, 1)[1] == [[0, 0, 2]]
for reason, paths in {"no entry path": PATHS[1:], "no way back from slot 2": PATHS[:4],
                      "a pair twice": PATHS + [dict(PATHS[1])], "an entry path to slot 1": [{"to": 1, "path": "e"}] + PATHS[1:],
                      "a path to its own slot": PATHS + [{"from": 1, "to": 1, "path": "e"}],
                      "a slot past the count": PATHS + [{"from": 1, "to": 3, "path": "e"}],
                      "an unknown key": [dict(PATHS[0], speed=2)] + PATHS[1:], "none": [],
                      "nine paths": PATHS + [{"from": 1, "to": 2, "path": "e"}] * 4}.items():
    try:
        fe.turn_paths(Fixture(CAMERAS), {"paths": paths}, 3)
    except ValueError:
        continue
    raise AssertionError("cooked the paths with " + reason)
for config in (dict(SELECT, front_clip="loop", turn="rotate", paths=PATHS),
               dict(SELECT, front_clip="loop", turn="path", paths=PATHS[:1],
                    slots=[dict(SELECT["slots"][0], turn_end=0.75)])):
    try:
        fe.select_scene(Fixture(CAMERAS), fe.Textures(Fixture({})), config, pathlib.Path("/nonexistent"))
    except ValueError as error:
        assert "select.paths: only in the path turn mode" in str(error) or "no turn_end" in str(error), error
        continue
    raise AssertionError(("cooked", config))
print("PASS front-end cook: the turn mode's names, 1298's .n3camera paths and their slots")

# RQ-095 (version 8): the select camera's fog, the one the path mode's camera
# files carry (CN3Camera::Load, 00439540), linear from 0.1 x far to far
# (004395c0); none in the rotate mode or without `fog`.
FOGGY = dict(CAMERAS, grey=n3camera(EYE, AT)[:-4] + struct.pack("<I", 0xFF808040),
             clear=n3camera(EYE, AT)[:-8] + struct.pack("<iI", 0, 0xFFFFFFFF))
fog_config = dict(turn="path", paths=PATHS, fog=True, camera=dict(far=500))
assert fe.path_fog(Fixture(FOGGY), fog_config) == u(1) + f([1, 1, 1, 50, 500])
grey = [dict(p, path="grey") for p in PATHS]
assert fe.path_fog(Fixture(FOGGY), dict(fog_config, paths=grey)) == u(1) + f([128 / 255, 128 / 255, 64 / 255, 50, 500])
off = u(0) + f([0] * 5)
assert fe.path_fog(Fixture(FOGGY), dict(fog_config, paths=[dict(p, path="clear") for p in PATHS])) == off
assert fe.path_fog(Fixture(FOGGY), {"turn": "rotate"}) == off
for reason, config in {"two fogs": dict(fog_config, paths=PATHS[:1] + grey[1:]),
                       "the rotate mode": dict(fog_config, turn="rotate"), "not true": dict(fog_config, fog=1)}.items():
    try:
        fe.path_fog(Fixture(FOGGY), config)
    except ValueError:
        continue
    raise AssertionError("cooked a fog with " + reason)

# RQ-095: a zone as the select hall (`select.zone`, a Zones.tbl key), on an
# original synthetic 33-sample zone (tools/assetc/ko_large_zone_fixture.py):
# its terrain and static shapes grouped into meshes by texture, light and
# blend, KO's coordinates with z negated, an alpha part BLEND with its sort
# point, an RF_NOTUSELIGHT part UNLIT; the files recorded through the tree.
import csv  # noqa: E402
import ko_character  # noqa: E402
import ko_large_zone_fixture as large_zone  # noqa: E402
import ko_shapes  # noqa: E402
import ko_shapes_fixture  # noqa: E402

import ko_terrain_fixture  # noqa: E402

zone_root = ROOT / "build/front-end-zone-test"
large_zone.write(zone_root, samples=33, object_textures=2, name="vale")
two_layers = (zone_root / "Zones/vale.gtd").read_bytes()
fixture_tile, references = ko_terrain_fixture.tile, large_zone.REFERENCES
try:  # one tile layer, as karus_intro's: 512 references, every tex2 past them
    large_zone.REFERENCES = references[:512]
    ko_terrain_fixture.tile = lambda x, z, n: dict(fixture_tile(x, z, n), tex1=(z * n + x) % 512, tex2=1023)
    large_zone.write(zone_root, samples=33, object_textures=2, name="vale")
finally:
    ko_terrain_fixture.tile, large_zone.REFERENCES = fixture_tile, references
MATERIAL = (0.5, 0.5, 0.5, 1.0)  # the terrain's Ambient (0059cd90)


def zone_shapes(ambient=MATERIAL):
    mesh, stone = "orig_pyramid.n3pmesh", ("orig_stone_0.dxt",)
    return ko_shapes_fixture.build(name="vale", width=128.0, depth=128.0, shapes=[
        dict(label="plain", position=(40.0, 1.0, 30.0), scale=(2.0, 2.0, 2.0), ambient=ambient,
             parts=((mesh, stone, 0.0),)),
        dict(label="glass", position=(80.0, 1.0, 90.0), ambient=ambient,
             parts=((mesh, ("orig_stone_1.dxt",), 0.0, ko_shapes.RF_ALPHABLENDING),)),
        dict(label="lamp", position=(20.0, 1.0, 100.0), ambient=ambient,
             parts=((mesh, stone, 0.0, ko_shapes.RF_NOTUSELIGHT),))])


(zone_root / "Zones/vale.opd").write_bytes(zone_shapes())
(zone_root / "Zones/vale.tlt").write_bytes(bytes(8))
(zone_root / "Data").mkdir(exist_ok=True)


def zone_table(opdext="Reserved"):
    row = ["10001", "Zones\\vale.gtd", "vale", "Zones\\vale.tct", "Zones\\vale.tlt", "Zones\\vale.opd", opdext,
           "Zones\\vale.dxt", "Misc\\Sky\\Field.N3Sky"] + ["0"] * 15
    with (zone_root / "Data/Zones.tbl.csv").open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows([["1 - UInt32"] + ["%d - String" % c for c in range(2, 25)], row])


zone_table()
zone_tree = ko_character.Assets(zone_root)
zone_textures, zone_report = fe.Textures(fe.Inputs([zone_tree])), {}
section = fe.zone(fe.Inputs([zone_tree]), zone_textures, 10001, zone_report)
at, meshes = 4, []
for _ in range(struct.unpack_from("<I", section)[0]):
    tex, flags = struct.unpack_from("<2I", section, at)
    nv = struct.unpack_from("<I", section, at + 32)[0]
    points = [struct.unpack_from("<3f", section, at + 36 + 32 * i) for i in range(nv)]
    at += 36 + 32 * nv
    ni = struct.unpack_from("<I", section, at)[0]
    at += 4 + 4 * ni
    meshes.append((tex, flags, points, ni, struct.unpack_from("<3f", section, at)))
    at += 12
assert at == len(section), (at, len(section))
flags = sorted(m[1] for m in meshes)
assert flags.count(fe.BLEND) == 1 and fe.CUT_ZERO | fe.UNLIT in flags and fe.CUT_ZERO in flags, flags
assert all(m[1] in (fe.CUT_ZERO, fe.CUT_ZERO | fe.UNLIT, fe.BLEND, fe.BLEND | fe.UNLIT) for m in meshes), flags
every = [p for m in meshes for p in m[2]]
assert all(-1 <= x <= 129 and -129 <= z <= 1 for x, _, z in every), "not KO's coordinates with z negated"
blend = next(m for m in meshes if m[1] == fe.BLEND)
assert all(78 <= x <= 82 and -92 <= z <= -88 for x, _, z in blend[2]), blend[2]
assert 78 <= blend[4][0] <= 82 and -92 <= blend[4][2] <= -88, ("sort point", blend[4])
assert zone_report["zone"]["key"] == 10001 and zone_report["zone"]["meshes"] == len(meshes), zone_report
assert {"Data/Zones.tbl.csv", "Zones/vale.gtd", "Zones/vale.tct", "Zones/vale.opd", "Object/orig_pyramid.n3pmesh",
        "Object/orig_stone_0.dxt", "Object/orig_stone_1.dxt"} <= set(zone_tree.sources), sorted(zone_tree.sources)
assert fe.zone(fe.Inputs([zone_tree]), zone_textures, None, {}) == u(0)
# The cook's totals: one vertex or index under the zone's own, or one mesh
# fewer, is refused (the caps are read at call time).
for cap, value, expect in (("MAX_ZONE_VERTICES", sum(len(m[2]) for m in meshes) - 1, "vertices or"),
                           ("MAX_ZONE_INDICES", sum(m[3] for m in meshes) - 1, "indices"),
                           ("MAX_ZONE_MESHES", len(meshes) - 1, "meshes, not 1 to")):
    saved = getattr(fe, cap)
    setattr(fe, cap, value)
    try:
        fe.zone(fe.Inputs([zone_tree]), fe.Textures(fe.Inputs([zone_tree])), 10001, {})
        raise AssertionError("cooked a zone past " + cap)
    except ValueError as error:
        assert expect in str(error), (cap, error)
    finally:
        setattr(fe, cap, saved)
for reason, setup, value, expect in [
        ("a part's material other than the terrain's", lambda: (zone_root / "Zones/vale.opd").write_bytes(
            zone_shapes(ambient=(0.0, 0.0, 0.0, 0.0))), 10001, "not the terrain's"),
        ("a second tile layer", lambda: ((zone_root / "Zones/vale.opd").write_bytes(zone_shapes()),
                                         (zone_root / "Zones/vale.gtd").write_bytes(two_layers)),
         10001, "a second tile layer"),
        ("an OPDEXT", lambda: zone_table("Zones\\vale.opdext"), 10001, "OPDEXT"),
        ("a key the table lacks", lambda: zone_table(), 10002, "no row"),
        ("a key that is not a number", lambda: None, "ten", "a Zones.tbl key")]:
    setup()
    try:
        fe.zone(fe.Inputs([ko_character.Assets(zone_root)]), fe.Textures(fe.Inputs([zone_tree])), value, {})
    except ValueError as error:
        assert expect in str(error), (reason, error)
        continue
    raise AssertionError("cooked a zone with " + reason)
try:
    fe.select_scene(Fixture(CAMERAS), fe.Textures(Fixture({})), dict(SELECT, hall="h.n3shape", zone=10001),
                    pathlib.Path("/nonexistent"))
    raise AssertionError("cooked a hall and a zone")
except ValueError as error:
    assert "a hall or a zone, not both" in str(error), error
shutil.rmtree(zone_root)
print("PASS front-end cook: the camera files' fog, a synthetic zone hall's meshes and its refusals")


# RQ-095: select.light_manager's lights replace the hall lights of their
# number (1298's select tick applies the hall lights, then its light
# manager's), in number order; without it the hall lights are as before.
def n3light(number, on=1, x=6.0):
    """A synthetic .n3light (CN3Light::Load): a still transform, then a point
    light's D3DLIGHT9 values, bOn and the light number."""
    return (string("light") + f([x, 1, 0, 0, 0, 0, 1, 1, 1, 1]) + u(0) * 3 + u(fe.POINT) +
            f([.7, .7, .7, 1] + [0] * 4 + [.5, .5, .5, 1] + [x, 1, 0] + [0, 0, 1] + [7, 0, 2, 0, 0, 0, 0]) +
            struct.pack("<2i", on, number))


HALL_LIGHTS = Fixture({"l0.n3light": n3light(0), "l1.n3light": n3light(1, x=-6.0), "l3.n3light": n3light(3),
                       "off.n3light": n3light(2, on=0)})
SUN = {"number": 0, "kind": "directional", "diffuse": [.8, .8, .8], "ambient": [.56, .56, .56],
       "direction": [0, -1, 0]}
LAMP = {"number": 2, "kind": "point", "diffuse": [.3, .3, .3], "ambient": [.21, .21, .21], "position": [1, 2, 3],
        "range": 128, "falloff": 1, "attenuation": [.5, 1 / 64, 1 / 2048]}
names = ["l0.n3light", "l1.n3light", "l3.n3light", "off.n3light"]
hall_only = fe.lights(HALL_LIGHTS, names)
assert hall_only == fe.lights(HALL_LIGHTS, names, None) and hall_only[:4] == u(3), hall_only[:4]
mixed = fe.lights(HALL_LIGHTS, names, [LAMP, SUN])
records = [mixed[4 + i * 80:4 + (i + 1) * 80] for i in range(4)]
assert mixed[:4] == u(4) and len(mixed) == 4 + 4 * 80, len(mixed)
sun = struct.unpack("<I19f", records[0])
assert sun[0] == fe.DIRECTIONAL and sun[10:13] == (0, -1, 0) and sun[13] == 1 and sun[15:18] == (1, 0, 0), sun
assert records[1] == hall_only[4 + 80:4 + 2 * 80], "hall light 1 kept"
lamp = struct.unpack("<I19f", records[2])
assert lamp[0] == fe.POINT and lamp[7:10] == (1, 2, -3) and lamp[13:15] == (128, 1), lamp  # KO z reflected
assert records[3] == hall_only[4 + 2 * 80:], "hall light 3 kept"
for bad, reason in (([dict(SUN, number=8)], "light numbers"), ([SUN, dict(LAMP, number=0)], "light numbers"),
                    ([dict(SUN, position=[0, 0, 0])], "a point light"), ([dict(LAMP, kind="spot")], "a point light"),
                    ([dict(SUN, diffuse=[2, 1, 1])], "colours 0 to 1"), ([dict(SUN, direction=[0, 0, 0])],
                                                                         "without a direction"),
                    ([dict(LAMP, range=0)], "range/attenuation"), ([dict(LAMP, attenuation=[0, 0, 0])],
                                                                    "range/attenuation"),
                    ([dict(LAMP, falloff="1")], "invalid vector"), ({"0": SUN}, "a list of at most 8"),
                    ([SUN] * 9, "a list of at most 8")):
    try:
        fe.lights(HALL_LIGHTS, names, bad)
    except ValueError as error:
        assert reason in str(error), (reason, error)
        continue
    raise AssertionError("cooked light_manager lights with " + reason)
print("PASS front-end cook: select.light_manager lights replace the hall lights of their number, %d refusals" % 11)
# A front-end clip past its joint's keys holds the last key there (1298's
# upc_ka_tu.n3anim clip 2); every other caller is refused, as before.
import ko_character  # noqa: E402
KEYS = {"rate": 15.0, "values": [[0, 0, 0], [1, 0, 0], [2, 0, 0]], "kind": 0}
assert ko_character.sample(KEYS, 5.0, None) == [2, 0, 0]  # key 2.5: the last key, as KO's 00427640
assert ko_character.sample(KEYS, 9.0, None, hold=True) == [2, 0, 0]
try:
    ko_character.sample(KEYS, 8.0, None)
    raise AssertionError("sampled past the keys without hold")
except ValueError as error:
    assert str(error) == "clip outside key range", error
print("PASS front-end cook: the front-clip mode's names, a clip held past its keys")

demo = ROOT / "build/packages/demo/scene.bin"
model = demo.read_bytes()
assert model[:4] == b"N3S1", demo
FONT = (512, 192, bytes(512 * 192 * 4))
CAMERA = f([0, 1, -3, 0, 1, 0, 0, 1, 0, 0.9, 0.1, 32])
LIGHT = dict(kind=fe.POINT, diffuse=[1, 1, 1], ambient=[0, 0, 0], position=[0, 2, -2], direction=[0, 0, 1],
             range=1e7, falloff=1, attenuation=[1, 0, 0], theta=0, phi=0)
MESH = fe.mesh_record([[0, 0, 0, 0, 1, 0, 0, 0], [1, 0, 0, 0, 1, 0, 1, 0], [0, 0, 1, 0, 1, 0, 0, 1]],
                      [0, 1, 2], 0, fe.DOUBLE_SIDED, [1, 1, 1], [1, 1, 1])


def raw_light(l):
    """A light record without the cook's checks (the loader's to refuse)."""
    return u(l["kind"]) + f(l["diffuse"] + l["ambient"] + l["position"] + l["direction"] +
                            [l["range"], l["falloff"]] + l["attenuation"] + [l["theta"], l["phi"]])


NO_MUSIC = u(0) + u(fe.NO_MUSIC) * 4


def track(data=TRACK, rate=48000, channels=1, loop=1, frames=None, kind=None, restart=0.0):
    """A version 5 track record: MPEG frames by default, `kind` PCM for
    16-bit samples (`frames` sample frames)."""
    pcm = kind == fe.PCM
    if frames is None:
        frames = len(data) // (2 * channels) if pcm else len(data) // 96
    head = u(fe.MPEG if kind is None else kind) + u(rate) + u(channels) + u(loop)
    restart = struct.pack("<I", restart) if type(restart) is int else f([restart])
    return head + restart + u(frames) + u(len(data)) + data


def pcm_track(data=PCM, rate=22050, channels=2, kind=fe.PCM, frames=None, **kw):
    """A PCM track record; `kind` other than PCM sizes it as PCM still."""
    return track(data, rate, channels, kind=kind, frames=len(data) // (2 * channels) if frames is None else frames,
                 **kw)


_, TRACKS, _ = fe.scene_tracks(model)


def character(clips=1, blends=None, plug=None):
    """A model record (version 4): the demo character, `clips` - 1 further
    clips (its own tracks again), each clip's blend time, the plugs."""
    plugs = u(0) if plug is None else u(1) + u(plug) + MESH
    further = (u(len(TRACKS)) + TRACKS) * (clips - 1)
    return u(len(model)) + model + u(clips - 1) + further + f([0.3] * clips if blends is None else blends) + plugs


def path(source=fe.ENTRY, to=0, eye_rate=30.0, eye=((0, 1, 2), (0, 1, 3)), at_rate=30.0, at=((0, 0, 0),)):
    """A version 7 path record (RQ-087)."""
    return (u(source) + u(to) + f([eye_rate]) + u(len(eye)) + b"".join(f(list(v)) for v in eye) + f([at_rate]) +
            u(len(at)) + b"".join(f(list(v)) for v in at))


PATHS3 = path() + path(0, 1) + path(0, 2) + path(1, 0) + path(2, 0)


def zone_mesh(flags=fe.CUT_ZERO, sort=(0, 0, 5), triangles=1):
    """A version 8 zone mesh (RQ-095): a mesh record (one triangle drawn
    `triangles` times) and its sort point."""
    return fe.mesh_record([[0, 0, 0, 0, 1, 0, 0, 0], [1, 0, 0, 0, 1, 0, 1, 0], [0, 0, 1, 0, 1, 0, 0, 1]],
                          [0, 1, 2] * triangles, 0, flags, [1, 1, 1], [.5, .5, .5]) + f(list(sort))


def truncated_zone():
    """A blob that ends four bytes into its one zone mesh's sort point."""
    data, mesh = blob(hall=0, zone=u(1) + zone_mesh()), zone_mesh()
    return data[:data.index(mesh) + len(mesh) - 8]


# The zone's index total, N3W1's 589,824: three meshes of 196,608 (the per-mesh
# bound) reach it; a fourth index mesh passes it.
MAX_INDEX_MESH = zone_mesh(triangles=65536)
# The vertex total, 196,608: three meshes of 65,536 vertices (the per-mesh
# bound) reach it; a fourth mesh passes it.
MAX_VERTEX_MESH = fe.mesh_record([[i % 256, 0, i // 256, 0, 1, 0, 0, 0] for i in range(65536)], [0, 1, 256], 0,
                                 fe.CUT_ZERO, [1, 1, 1], [.5, .5, .5]) + f([0, 0, 5])


FOG_OFF = u(0) + f([0] * 5)


# Version 11 (RQ-106): no moves and KO's unscaled placement.
NO_PLACEMENT = u(0) + u(0) * 6


def blob(version=25, slots=1, screen_data=None, font_index=None, light=None, plug=None, extra=b"", slot_count=None,
         canvas=(1024, 768), magic=b"N3FE", strings=None, music=NO_MUSIC, select_clips=3, blends=None,
         spot_rate=0.6, front_clip=0, escape=0, back=0, arrows=0, create=0, create_yaws=None, turn=0, paths=None, hall=1,
         zone=u(0), fog=FOG_OFF, more_textures=0, logo=u(0), messages=u(0), placement=NO_PLACEMENT, slide=u(0),
         creates=None, choices=u(0) + u(0)):
    tex = [(w, h, rgba) for w, h, rgba in textures.list] + [(1, 1, bytes(4))] * more_textures + [FONT]
    out = magic + u(version) + u(slots) + u(canvas[0]) + u(canvas[1])
    out += u(len(tex)) + b"".join(u(w) + u(h) + rgba for w, h, rgba in tex)
    out += u(1) + u(len(tex) - 1 if font_index is None else font_index) + u(16) + u(12) + u(4) + f([6] * 95)
    out += b"".join(screen_data or screens)
    out += b"".join(string(s) for s in (strings or ["Level: {level}", "ENTER", "Priest", "Heals.", "Loading",
                                                    "Ver. {version}"]))
    lights = u(1) + raw_light(light or LIGHT)
    out += CAMERA + lights + f([0, 0, 0]) + character(plug=plug, blends=blends) + u(0) + f([100, 50, 400, 350])
    spot = dict(LIGHT, kind=fe.SPOT, theta=0.5, phi=0.6, range=6.0)
    out += CAMERA + u(0) + f([0, 0, 0]) + u(slots if slot_count is None else slot_count)
    out += (f([0, -1, 2, 0, 0, 0, 7]) + fe.light_record(spot)) * (slots if slot_count is None else slot_count)
    out += f([spot_rate]) + (b"" if front_clip is None else u(front_clip)) + (b"" if escape is None else u(escape))
    out += b"" if back is None else u(back)
    out += b"" if arrows is None else u(arrows)
    # Version 19 (RQ-125): where create draws, and over the hall each slot's
    # create yaw.
    if create is not None:
        out += u(create) + f(create_yaws if create_yaws is not None else [-3.75] * slots if create == 1 else [])
    if paths is None:
        paths = (u(5) + PATHS3 if slots == 3 else u(1) + path()) if turn == 1 else u(0)
    out += u(turn) + paths + u(hall) + MESH * hall + zone + fog
    out += character(select_clips, plug=plug)
    # Version 24 (RQ-158): the create models, each a race and a model record.
    out += u(1) + u(2) + character(plug=plug) if creates is None else creates
    # Version 20 (RQ-126): create's slide, after the placement; version 25
    # (RQ-172): create's race and class buttons, after the slide.
    return out + music + logo + messages + placement + slide + choices + extra


# --- the create models (version 24, RQ-158) -------------------------------------

import ko_create  # noqa: E402

# Without create rules, the select character's race alone; with Moradon's, it
# first and then the rest of models.create in the rules' races order.
assert fe.create_races(2) == [(2, None)]
moradon_rules = ko_create.rules(ROOT / "games/moradon")
ordered = fe.create_races(2, moradon_rules)
assert [race for race, _ in ordered] == moradon_rules["models"]["create"] == [2, 3, 4], ordered
assert [entry["looks"] for _, entry in ordered] == ["upc_ka_tu", "upc_ka_wt", "upc_ka_pu"], ordered
assert [race for race, _ in fe.create_races(4, moradon_rules)] == [4, 2, 3]
create_refusals = {
    "a select race without a create model": lambda: fe.create_races(13, moradon_rules),
    "no create models": lambda: fe.create_scene(None, [], pathlib.Path("/nonexistent")),
    "33 create models": lambda: fe.create_scene(None, [(r, None) for r in range(1, 34)], pathlib.Path("/nonexistent")),
    "a race twice": lambda: fe.create_scene(None, [(2, None), (2, None)], pathlib.Path("/nonexistent")),
    "race 0": lambda: fe.create_scene(None, [(0, None)], pathlib.Path("/nonexistent")),
    "race 65536": lambda: fe.create_scene(None, [(65536, None)], pathlib.Path("/nonexistent")),
}
for reason, call in create_refusals.items():
    try:
        call()
    except ValueError:
        continue
    raise AssertionError("front-end cook accepted " + reason)
print("PASS front-end cook: a create model per race of models.create, the select race first; %d refusals"
      % len(create_refusals))


# --- the logo screen (version 9, RQ-101) ---------------------------------------

LOGO_UIF = node(0, "root", [node(0, "g0", [node(4, rect=(0, 0, 1024, 768)), node(4)]),
                            node(0, "g1", [node(4), text("by")]), node(0, "g2", [node(4)])])[1]
LOGO = {"ui": "logo.uif", "place": "centre",
        "groups": [{"node": "g0", "seconds": 1.5}, {"node": "g1", "seconds": 1}, {"node": "g2", "seconds": 1.5}],
        "peak": 1.5, "music": {"track": 0, "delay": 1, "fade_group": 2, "fade": 4}, "skip": "key", "cursor": "hidden"}


def logo_section(config=LOGO, tracks=1, uif=LOGO_UIF):
    assets = Fixture({"logo.uif": uif})
    return fe.logo(config, assets, fe.Textures(assets), {}, tracks)


assert fe.logo(None, None, None, None, 0) == (u(0), None)
LOGO_OK, report = logo_section()
assert [(g["fade_in"], g["hold"], g["fade_out"]) for g in report["groups"]] == [(1.5, 1.5, 1.5), (1, 1, 1),
                                                                                 (1.5, 1.5, 1.5)], report
assert (report["music"], report["delay"], report["fade_group"], report["fade"]) == (0, 1, 2, 4), report
assert LOGO_OK[:4] == u(1) and LOGO_OK[-4:] == u(fe.LOGO_SKIP_KEY | fe.LOGO_HIDE_CURSOR), LOGO_OK[-8:]
# The root, three groups, four images and a string; g0, g1 and g2 at 1, 4 and 7.
LOGO_NODES, LOGO_INDICES = fe.screen("logo", LOGO, Fixture({"logo.uif": LOGO_UIF}), fe.Textures(None), {},
                                     ["g0", "g1", "g2"])
assert struct.unpack_from("<I", LOGO_NODES)[0] == 9 and LOGO_INDICES == [1, 4, 7], LOGO_INDICES
assert LOGO_OK == u(1) + LOGO_NODES + u(3) + b"".join(
    u(i) + f(t) for i, t in zip(LOGO_INDICES, ([1.5] * 3, [1] * 3, [1.5] * 3))) + u(0) + f([1]) + u(2) + f([4]) + u(3)
silent, report = logo_section({k: v for k, v in LOGO.items() if k not in ("music", "skip", "cursor")}, tracks=0)
assert silent.endswith(u(fe.NO_MUSIC) + f([0]) + u(fe.NO_GROUP) + f([0]) + u(0)) and report["music"] is None, report
logo_problems = {
    "an unknown key": dict(config={**LOGO, "bindings": {"g0": "ok"}}),
    "no groups": dict(config={**LOGO, "groups": []}),
    "nine groups": dict(config={**LOGO, "groups": [{"node": "g0", "seconds": 1}] * 9}),
    "a group that is an image": dict(config={**LOGO, "groups": [{"node": "g0#0", "seconds": 1}]}),
    "a group twice": dict(config={**LOGO, "groups": [{"node": "g0", "seconds": 1}, {"node": "g0", "seconds": 1}]}),
    "a hidden group": dict(config={**LOGO, "hidden": ["g1"]}),
    "a group of no seconds": dict(config={**LOGO, "groups": [{"node": "g0", "seconds": 0}]}),
    "a group past 60 s": dict(config={**LOGO, "groups": [{"node": "g0", "seconds": 21}]}),
    "a peak of 1": dict(config={**LOGO, "peak": 1}),
    "a music track past the tracks": dict(tracks=0),
    "a fade group without its fade": dict(config={**LOGO, "music": {"track": 0, "fade_group": 2}}),
    "a fade group past the groups": dict(config={**LOGO, "music": {"track": 0, "fade_group": 3, "fade": 4}}),
    "a fade of 0": dict(config={**LOGO, "music": {"track": 0, "fade_group": 2, "fade": 0}}),
    "a delay past 60 s": dict(config={**LOGO, "music": {"track": 0, "delay": 61}}),
    "an unknown skip": dict(config={**LOGO, "skip": "click"}),
    "an unknown cursor": dict(config={**LOGO, "cursor": "off"}),
    "a button in the layout": dict(uif=node(0, "root", [node(0, "g0", [button("b")]), node(0, "g1"),
                                                        node(0, "g2")])[1]),
}
for reason, kw in logo_problems.items():
    try:
        logo_section(**kw)
    except (ValueError, KeyError) as error:
        continue
    raise AssertionError("logo cook accepted " + reason)
print("PASS front-end logo cook: 1264's groups as fade-in, hold and fade-out, its music and flags; %d refusals"
      % len(logo_problems))


def logo_raw(groups=((1, 1.5, 1.5, 1.5), (4, 1, 1, 1), (7, 1.5, 1.5, 1.5)), music=0, delay=1.0, fade_group=2,
             fade=4.0, flags=3, nodes=None, count=None):
    out = u(1) + (nodes or LOGO_NODES) + u(len(groups) if count is None else count)
    out += b"".join(u(g[0]) + f(g[1:]) for g in groups)
    return out + u(music) + f([delay]) + u(fade_group) + f([fade]) + (b"" if flags is None else u(flags))


def logo_node_patched(index, offset, value):
    """LOGO_NODES with node `index`'s u32 at `offset` (0 kind, then past the
    rect and id: the action) set to `value`."""
    data = bytearray(LOGO_NODES)
    at = 4
    for _ in range(index):
        at = fe.node_end(bytes(data), at)
    if offset == "action":
        at += 4 + 4 + 16
        offset = 4 + struct.unpack_from("<I", data, at)[0]
    struct.pack_into("<I", data, at + offset, value)
    return bytes(data)


# --- the message titles (version 10, RQ-102, Q81) ------------------------------

import ko_tbl  # noqa: E402

# A synthetic client text table (row id, text) as KO's Data/Texts_us.tbl is
# laid out and encrypted; row 3 holds a byte outside ASCII.
texts_plain = bytearray(ko_tbl.build(fe.TEXT_TYPES, [[1, "Failed"], [2, "Enter a name. "], [3, "caf?"]]))
texts_plain[-1] = 0xE9
TEXTS = Fixture({"Data/Texts.tbl": ko_tbl.encrypt(bytes(texts_plain)),
                 "Data/Wide.tbl": ko_tbl.encrypt(ko_tbl.build([5, 7], [[1, "Failed"]]))})
TITLED = {"bindings": {"text_msg": "message", "text_title": "title", "btn_ok": "ok"}}


def messages(worded, bindings=TITLED, assets=TEXTS):
    return fe.messages_section({"screens": {"message": bindings}, "messages": worded}, assets)


row = lambda n, table="Data/Texts.tbl": {"table": table, "row": n}  # noqa: E731
MESSAGES_OK, message_report = messages({"create_name": {"title": row(1), "text": row(2)},
                                "create_refused": {"title": row(1)},
                                "login": {"text": "Realm words."}})
assert message_report == {"create_name": {"title": "Failed", "text": "Enter a name. "},
                  "create_refused": {"title": "Failed", "text": None},
                  "login": {"title": "", "text": "Realm words."}}, report
# In MESSAGES order, whatever the recipe's: login (2), create_name (5), create_refused (6).
assert MESSAGES_OK == (u(3) + u(2) + string("") + u(1) + string("Realm words.") +
                       u(5) + string("Failed") + u(1) + string("Enter a name. ") +
                       u(6) + string("Failed") + u(0) + string("")), MESSAGES_OK
assert messages({}) == (u(0), {}) and fe.messages_section({"screens": {}}, None) == (u(0), {})
# No title needs no `title` binding.
assert messages({"login": {"text": "x"}}, bindings={"bindings": {}})[0] == u(1) + u(2) + string("") + u(1) + string("x")
message_problems = {
    "an unknown kind": dict(worded={"logo": {"title": "x"}}),
    "an empty entry": dict(worded={"login": {}}),
    "an unknown key": dict(worded={"login": {"title": "x", "colour": 1}}),
    "a title without a title binding": dict(worded={"login": {"title": "x"}}, bindings={"bindings": {}}),
    "a row the table lacks": dict(worded={"login": {"title": row(9)}}),
    "a row outside ASCII": dict(worded={"login": {"title": row(3)}}),
    "a table of other columns": dict(worded={"login": {"title": row(1, "Data/Wide.tbl")}}),
    "a row id of 0": dict(worded={"login": {"title": row(0)}}),
    "a row id as a string": dict(worded={"login": {"title": {"table": "Data/Texts.tbl", "row": "1"}}}),
    "a missing table": dict(worded={"login": {"title": row(1, "Data/None.tbl")}}),
    "a text of a control byte": dict(worded={"login": {"text": "a\tb"}}),
    "a text past 1024 bytes": dict(worded={"login": {"text": "x" * 1025}}),
    "a number": dict(worded={"login": {"title": 1901}}),
    # RQ-111 (version 14): exit_confirm asks yes or no, so the box binds both.
    "exit_confirm without yes and no": dict(worded={"exit_confirm": {"text": "Exit?"}}),
    "exit_confirm without no": dict(worded={"exit_confirm": {"text": "Exit?"}},
                                    bindings={"bindings": {**TITLED["bindings"], "btn_yes": "yes"}}),
}
for reason, kw in message_problems.items():
    try:
        messages(**kw)
    except (ValueError, KeyError):
        continue
    raise AssertionError("message cook accepted " + reason)
# RQ-111: exit_confirm with the box's yes and no bound, last in MESSAGES order.
QUESTION_BINDINGS = {"bindings": {**TITLED["bindings"], "btn_yes": "yes", "btn_no": "no"}}
EXIT_CONFIRM, _ = messages({"exit_confirm": {"text": row(2)}}, bindings=QUESTION_BINDINGS)
EXIT_INDEX = fe.MESSAGES.index("exit_confirm")
assert EXIT_INDEX == 10 and \
    EXIT_CONFIRM == u(1) + u(EXIT_INDEX) + string("") + u(1) + string("Enter a name. "), EXIT_CONFIRM
# RQ-130 (version 21): create's two refusals follow it, the engine's
# FrontMessage order (client/assets/assets.h).
assert fe.MESSAGES[11:] == ("create_no_race", "create_no_class"), fe.MESSAGES
# The recipe's tables are paths the choice's prefix check sees (RQ-084).
assert ("messages.login.title.table", "installer-1264:Data/Texts_us.tbl") in fe.recipe_paths(
    {"messages": {"login": {"title": {"table": "installer-1264:Data/Texts_us.tbl", "row": 1}}}})
print("PASS front-end message cook: titles and texts from a KO text table's rows or the recipe; %d refusals"
      % len(message_problems))


def message_raw(*entries, count=None):
    """A version 10 message section: (kind, title, replaces, text) entries."""
    out = u(len(entries) if count is None else count)
    return out + b"".join(u(k) + string(t) + u(r) + string(x) for k, t, r, x in entries)


# RQ-111 (version 14): the synthetic screens with a message box of KO's
# Btn_Yes and Btn_No (El_MessageBox_us.uif's), and with yes or no cooked off
# the message box (without the cook's own check) for the loader's.
def question_screens(no=True):
    tree = node(0, "root", [text("text_msg"), button("btn_ok"), button("btn_yes")] + [button("btn_no")] * no)
    bindings = {**BINDINGS["message"], "btn_yes": "yes", **({"btn_no": "no"} if no else {})}
    return cook_screens(trees={**trees, "message.uif": tree[1]},
                        specs={**{n: spec(n) for n in fe.SCREENS}, "message": spec("message", bindings=bindings)})[0]


def yes_off_message():
    specs = {n: spec(n) for n in fe.SCREENS}
    specs["login"]["bindings"]["notice"] = "yes"
    saved = dict(fe.ONLY_ON)
    fe.ONLY_ON.clear()
    try:
        return cook_screens(specs=specs)[0]
    finally:
        fe.ONLY_ON.update(saved)


QUESTION = question_screens()
assert struct.unpack_from("<I", QUESTION[4])[0] == 1 + 1 + 6 * 3, struct.unpack_from("<I", QUESTION[4])
MESSAGE_CASES = {
    "ok-messages": blob(messages=MESSAGES_OK),
    "ok-messages-every": blob(screen_data=QUESTION,
                              messages=message_raw(*((k, "t", 0, "") for k in range(len(fe.MESSAGES))))),
    "ok-exit-confirm": blob(screen_data=QUESTION, messages=EXIT_CONFIRM),
    "ok-question-box-unused": blob(screen_data=QUESTION),
    "bad-exit-confirm-no-buttons": blob(messages=EXIT_CONFIRM),
    "bad-exit-confirm-no-no": blob(screen_data=question_screens(no=False), messages=EXIT_CONFIRM),
    "bad-yes-off-message": blob(screen_data=yes_off_message()),
    "bad-messages-over": blob(messages=message_raw(*((k % len(fe.MESSAGES), "t", 0, "")
                                                     for k in range(len(fe.MESSAGES) + 1)))),
    "bad-message-kind": blob(messages=message_raw((len(fe.MESSAGES), "t", 0, ""))),
    "bad-message-twice": blob(messages=message_raw((1, "t", 0, ""), (1, "u", 0, ""))),
    "bad-message-replaces": blob(messages=message_raw((1, "t", 2, ""))),
    "bad-message-text-unused": blob(messages=message_raw((1, "t", 0, "x"))),
    "bad-message-title-byte": blob(messages=u(1) + u(1) + u(1) + b"\x01" + u(0) + string("")),
    "bad-message-title-long": blob(messages=message_raw((1, "x" * 1025, 0, ""))),
    "bad-message-text-long": blob(messages=message_raw((1, "", 1, "x" * 1025))),
    "bad-message-truncated": blob(messages=MESSAGES_OK[:-4]),
    "bad-messages-missing": blob(messages=b""),
}

ONE_TRACK = u(1) + track() + u(0) * 3 + u(fe.NO_MUSIC)
LOGO_CASES = {
    "ok-logo": blob(music=ONE_TRACK, logo=LOGO_OK),
    "ok-logo-silent": blob(logo=silent),
    "ok-logo-raw": blob(music=ONE_TRACK, logo=logo_raw()),
    "ok-logo-no-fade": blob(music=ONE_TRACK, logo=logo_raw(fade_group=fe.NO_GROUP, fade=0.0, flags=0)),
    "bad-logo-flag": blob(logo=u(2)),
    "bad-logo-music": blob(logo=LOGO_OK),
    "bad-logo-action": blob(music=ONE_TRACK, logo=logo_raw(nodes=logo_node_patched(2, "action", 19))),
    "bad-logo-button": blob(music=ONE_TRACK, logo=logo_raw(nodes=logo_node_patched(0, 0, 2))),
    "bad-logo-groups-none": blob(music=ONE_TRACK, logo=logo_raw(groups=(), fade_group=fe.NO_GROUP, fade=0.0)),
    "bad-logo-groups-nine": blob(music=ONE_TRACK, logo=logo_raw(groups=[(1, 1, 1, 1)] * 9)),
    "bad-logo-group-image": blob(music=ONE_TRACK, logo=logo_raw(groups=((2, 1, 1, 1),), fade_group=0)),
    "bad-logo-group-past": blob(music=ONE_TRACK, logo=logo_raw(groups=((9, 1, 1, 1),), fade_group=0)),
    "bad-logo-group-twice": blob(music=ONE_TRACK, logo=logo_raw(groups=((1, 1, 1, 1), (1, 1, 1, 1)))),
    "bad-logo-time-negative": blob(music=ONE_TRACK, logo=logo_raw(groups=((1, -1, 1, 1),), fade_group=0)),
    "bad-logo-time-nan": blob(music=ONE_TRACK, logo=logo_raw(groups=((1, float("nan"), 1, 1),), fade_group=0)),
    "bad-logo-time-none": blob(music=ONE_TRACK, logo=logo_raw(groups=((1, 0, 0, 0),), fade_group=0)),
    "bad-logo-time-past": blob(music=ONE_TRACK, logo=logo_raw(groups=((1, 20, 20, 20.5),), fade_group=0)),
    "bad-logo-delay": blob(music=ONE_TRACK, logo=logo_raw(delay=61.0)),
    "bad-logo-fade-no-group": blob(music=ONE_TRACK, logo=logo_raw(fade_group=fe.NO_GROUP)),
    "bad-logo-fade-no-music": blob(logo=logo_raw(music=fe.NO_MUSIC)),
    "bad-logo-fade-zero": blob(music=ONE_TRACK, logo=logo_raw(fade=0.0)),
    "bad-logo-fade-group": blob(music=ONE_TRACK, logo=logo_raw(fade_group=3)),
    "bad-logo-flags": blob(music=ONE_TRACK, logo=logo_raw(flags=4)),
    "bad-logo-truncated": blob(music=ONE_TRACK, logo=logo_raw(flags=None)),
}


def unbound(name, action):
    """`screens` with `action`'s node in screen `name` left unbound (cooked
    without the cook's own check)."""
    saved = fe.REQUIRED[name]
    fe.REQUIRED[name] = saved - {action}
    try:
        node_id = next(k for k, v in BINDINGS[name].items() if v == action)
        specs = {n: spec(n) for n in fe.SCREENS}
        specs[name]["bindings"].pop(node_id)
        return cook_screens(specs=specs)[0]
    finally:
        fe.REQUIRED[name] = saved


def patched_action(screen_data, index, action):
    """Screen 0's first node bound to `action` (an index, unchecked)."""
    data = bytearray(screen_data[0])
    # count, kind, parent, rect (4 f), id (u32 length + bytes), action
    at = 4 + 4 + 4 + 16
    length = struct.unpack_from("<I", data, at)[0]
    struct.pack_into("<I", data, at + 4 + length, action)
    return [bytes(data)] + list(screen_data[1:])


# --- the placement (version 11, RQ-106, Q82) ------------------------------------

def frame(ident, kind, rect, children=()):
    """A node of `kind` at `rect`; a button's four state images share it."""
    if kind == 1:
        children = [node(4, reserved=k, rect=rect) for k in range(4)] + list(children)
    return node(kind, ident, children, rect=rect)


# Synthetic layouts at the rects of 1264's (KO-FINDINGS 9.3): the login's root
# 984 x 506 with its server group at the top-left and its copyright line
# (RQ-108), the select's buttons, the
# create's 1025-wide root, the loading's root at a negative origin with its
# version text, the message box.
PLACE_TREES = {
    "login.uif": frame("root", 0, (-1, 0, 983, 506), [
        frame("Group_LogIn", 0, (0, 0, 983, 505), [frame("Btn_Login", 1, (408, 470, 488, 492)),
                                                     frame("Btn_Cancel", 1, (496, 470, 576, 492))]),
        frame("Group_ServerList", 0, (12, 30, 218, 482), [frame("List_Server", 14, (20, 60, 200, 400)),
                                                            frame("Btn_Connect", 1, (40, 420, 180, 450))]),
        frame("Text_Rights", 6, (213, 307, 814, 332))])[1],
    "select.uif": frame("root", 0, (0, 0, 1024, 768), [
        frame("text00", 6, (716, 253, 910, 477)), frame("bt_back", 1, (419, 635, 619, 671)),
        frame("bt_exit", 1, (418, 685, 618, 721)), frame("bt_left", 1, (313, 686, 386, 722)),
        frame("bt_right", 1, (644, 684, 717, 720))])[1],
    "create.uif": frame("root", 0, (-1, 0, 1024, 788), [
        frame("btn_create", 1, (71, 677, 265, 713)), frame("btn_cancel", 1, (755, 677, 949, 713)),
        node(8, "edit_name", [node(4, texture="", rect=(413, 671, 677, 697)), node(6, rect=(413, 671, 677, 697))],
             rect=(413, 671, 677, 697)),
        frame("area_character", 9, (353, 59, 676, 632)), frame("text_desc", 6, (754, 357, 952, 630))])[1],
    "loading.uif": frame("root", 0, (-12, -20, 666, 413), [
        frame("Text_Version", 6, (4, 5, 165, 53)),
        frame("Progress_Loading", 3, (354, 378, 619, 396), [node(4, reserved=0, rect=(354, 378, 619, 396)),
                                                            node(4, reserved=1, rect=(354, 378, 619, 396))])])[1],
    "message.uif": frame("root", 0, (0, 0, 327, 156), [frame("text_msg", 6, (21, 28, 304, 86)),
                                                       frame("btn_ok", 1, (115, 116, 212, 145))])[1],
}
PLACE_BINDINGS = {**BINDINGS, "login": {**{k: v for k, v in BINDINGS["login"].items() if k != "notice"},
                                        "Text_Rights": "login_closed"},
                  "loading": {"Progress_Loading": "progress", "Text_Version": "version"}}
# games/moradon/front-end.json's placements of the 1264 layouts (and, but for
# the copyright line's, RQ-108, front-end-1298.json's).
PLACE_SPECS = {
    "login": {"place": "bottom", "moves": [{"node": "Group_ServerList", "x": 0, "y": 0},
                                           {"node": "Text_Rights", "x": "centre", "bottom": 20}]},
    "select": {"place": "origin", "moves": [
        {"node": "bt_left", "x": {"middle": -100, "ratio": -26, "edge": "end"}, "bottom": 10},
        {"node": "bt_right", "x": {"middle": 100, "ratio": 26}, "bottom": 10},
        {"node": "bt_exit", "x": "centre", "bottom": 10},
        {"node": "bt_back", "x": "centre", "above": ["bt_exit", 10]}]},
    "create": {"place": "centre"},
    "loading": {"place": "centre", "moves": [{"node": "Text_Version", "x": 10, "y": 10}]},
    "message": {"place": "centre"},
}


# RQ-109 (KO-FINDINGS 9.6): 1298's select bar at co_CharacterSelect_us.uif's
# rects, 1024 x 113, and front-end-1298.json's placement of it.
BAR_PLACE_TREE = frame("root", 0, (0, 0, 1024, 113), [
    frame("btn_create", 1, (28, 57, 178, 91)), frame("btn_start", 1, (233, 57, 383, 91)),
    frame("btn_delete", 1, (435, 56, 585, 90)), frame("btn_back", 1, (645, 56, 795, 90)),
    frame("btn_exit", 1, (846, 56, 996, 90)), frame("str_id", 6, (431, 23, 629, 40)),
    frame("str_lev", 6, (158, 24, 184, 40)), frame("str_job", 6, (760, 25, 918, 41)),
    frame("btn_left", 1, (27, 23, 64, 41)), frame("btn_right", 1, (958, 23, 995, 41))])[1]
BAR_PLACE_SPEC = {"place": {"bottom": 10}}
# RQ-125 (KO-FINDINGS 9.15): 1298's in-select create at
# co_characterCreate_us.uif's rects, its 291 x 705 root and its three panels,
# and front-end-1298.json's placement of them: the root at the origin
# (005fab40's SetPos(0, 0)), each panel where 1298's Tick (00606450) clamps its
# slide: Group_class 50 from the left, Group_race 50 from the right, Group_name
# centred (Load 00603850's x), each bottom 30 above the window's.
HALL_CREATE_PLACE_TREE = frame("root", 0, (0, 0, 291, 705), [
    frame("Group_race", 0, (0, 1, 214, 705), [frame("text_desc", 6, (33, 268, 178, 554)),
                                              frame("btn_create", 1, (34, 567, 183, 601)),
                                              frame("btn_cancel", 1, (34, 606, 183, 640))]),
    frame("Group_class", 0, (-1, 0, 215, 702), [frame("str_01", 6, (32, 320, 89, 342))]),
    frame("Group_name", 0, (0, 0, 363, 72), [
        node(8, "edit_name", [node(4, texture="", rect=(121, 21, 315, 48)), node(6, rect=(121, 21, 315, 48))],
             rect=(121, 21, 315, 48))])])[1]
HALL_CREATE_PLACE_SPEC = {"place": "origin", "moves": [{"node": "Group_class", "x": 50, "bottom": 30},
                                                       {"node": "Group_race", "right": 50, "bottom": 30},
                                                       {"node": "Group_name", "x": "centre", "bottom": 30}]}
HALL_CREATE_BINDINGS = {"btn_create": "create_confirm", "btn_cancel": "back", "edit_name": "name_field",
                        "text_desc": "class_desc"}


def cook_placed(specs=PLACE_SPECS, trees=PLACE_TREES, bindings=PLACE_BINDINGS, over_hall=False, slides=None):
    assets = Fixture(trees)
    textures, fonts, placements = fe.Textures(assets), {}, []
    data = [fe.screen(n, {"ui": n + ".uif", "bindings": dict(bindings[n]), **specs[n]}, assets, textures,
                      fonts, placements=placements, slides=slides,
                      **(UNVIEWED if over_hall and n == "create" else {}))
            for n in fe.SCREENS]
    return data, placements


def cook_placed_bar(specs=None):
    specs = specs or {**PLACE_SPECS, "select": BAR_PLACE_SPEC}
    return cook_placed(specs, {**PLACE_TREES, "select.uif": BAR_PLACE_TREE},
                       {**PLACE_BINDINGS, "select": BAR_BINDINGS})


def cook_placed_1298(specs=None, slides=None):
    """The 1298 recipe's layouts: 1298's select bar and its in-select create."""
    specs = specs or {**PLACE_SPECS, "select": BAR_PLACE_SPEC, "create": HALL_CREATE_PLACE_SPEC}
    return cook_placed(specs, {**PLACE_TREES, "select.uif": BAR_PLACE_TREE, "create.uif": HALL_CREATE_PLACE_TREE},
                       {**PLACE_BINDINGS, "select": BAR_BINDINGS, "create": HALL_CREATE_BINDINGS}, over_hall=True,
                       slides=slides)


def ko_rects(width, height, bar=False, hall_create=False):
    """KO's own placements of the layouts above at a viewport, written from the
    binaries (KO-FINDINGS 9.3), each node's top-left: 1264's login Init
    (005bde22: ((W - w) >> 1, H - h)), its server list tick (005c25b0:
    (0, 0) at rest) and SetVisibleLogInUIs (005c2820: the copyright line at
    ((W - w) / 2, H - h - 20), C's signed division); CUICharacterSelect::Load (004448f0, r = W / 1024 as a
    float); create (0043cd00) and loading (00401670) centred with C's signed
    division, the version at (10, 10) (00531c80); the message box
    ((W - w) >> 1, 0050c730)."""
    r = struct.unpack("<f", struct.pack("<f", width / 1024))[0]
    centre = lambda extent, size: int((extent - size) / 2)
    login_x, login_y = (width - 984) >> 1, height - 506
    return {
        "login": {"root": (login_x, login_y), "Btn_Login": (login_x + 409, login_y + 470),
                  "Group_ServerList": (0, 0), "List_Server": (8, 30),
                  "Text_Rights": (centre(width, 601), height - 25 - 20)},
        "select": {"root": (0, 0), "text00": (716, 253),
                   "bt_left": (int((width >> 1) - 73 - 100 - 26 * r), height - 10 - 36),
                   "bt_right": (int((width >> 1) + 26 * r + 100), height - 10 - 36),
                   "bt_exit": ((width - 200) >> 1, height - 10 - 36),
                   "bt_back": ((width - 200) >> 1, (685 - 721) + (635 - 671) + height - 20)},
        "create": {"root": (centre(width, 1025), centre(height, 788)),
                   "area_character": (centre(width, 1025) + 354, centre(height, 788) + 59)},
        "loading": {"root": (centre(width, 678), centre(height, 433)), "Text_Version": (10, 10),
                    "Progress_Loading": (centre(width, 678) + 366, centre(height, 433) + 398)},
        "message": {"root": ((width - 327) >> 1, (height - 156) >> 1)},
        # RQ-109: 1298's select bar (00606c10: its root at ((W - w) >> 1,
        # H - 10 - h), 006070bd-0060710a), its nodes carried with it.
        **({"select": {ident: (((width - 1024) >> 1) + x, height - 10 - 113 + y) for ident, (x, y) in (
            ("root", (0, 0)), ("btn_create", (28, 57)), ("btn_start", (233, 57)), ("btn_delete", (435, 56)),
            ("btn_back", (645, 56)), ("btn_exit", (846, 56)), ("str_id", (431, 23)), ("str_lev", (158, 24)),
            ("str_job", (760, 25)), ("btn_left", (27, 23)), ("btn_right", (958, 23)))}} if bar else {}),
        # RQ-125: 1298's in-select create (005fab40: the root at (0, 0)), its
        # panels where Load (00603850) and Tick (00606450) clamp them:
        # Group_class at (50, H - 30 - h), Group_race at (W - w - 50,
        # H - 30 - h), Group_name at ((W - w) / 2, H - 30 - h), each child
        # carried with its panel.
        **({"create": {"root": (0, 0), "Group_class": (50, height - 30 - 702),
                       "str_01": (50 + 33, height - 30 - 702 + 320),
                       "Group_race": (width - 214 - 50, height - 30 - 704),
                       "btn_create": (width - 214 - 50 + 34, height - 30 - 704 + 566),
                       "Group_name": ((width - 363) // 2, height - 30 - 72),
                       "edit_name": ((width - 363) // 2 + 121, height - 30 - 72 + 21)}} if hall_create else {}),
    }


placed_screens, placements = cook_placed()
# At the canvas the moves are where the canvas rects are: the cook's rects are
# KO's at 1024 x 768 (1264's select: bt_right at 638, exit and back at 412).
canvas_rects = ko_rects(1024, 768)
assert len(placements) == 5 and [struct.unpack_from("<I", p)[0] for p in placements] == [3, 5, 1, 2, 1], placements


def placed_nodes(screens):
    """{screen: {id: (index, canvas rect)}} of the named nodes (and the root)."""
    out = {n: {} for n in fe.SCREENS}
    for n, data in zip(fe.SCREENS, screens):
        at = 4
        for i in range(struct.unpack_from("<I", data)[0]):
            rect = struct.unpack_from("<4f", data, at + 8)
            length = struct.unpack_from("<I", data, at + 24)[0]
            ident = data[at + 28:at + 28 + length].decode() or ("root" if i == 0 else "")
            if ident and ident not in out[n]:
                out[n][ident] = (i, rect)
            at = fe.node_end(data, at)
    return out


PLACED_NODES = placed_nodes(placed_screens)
for n, want in canvas_rects.items():
    for ident, xy in want.items():
        assert PLACED_NODES[n][ident][1][:2] == xy, (n, ident, PLACED_NODES[n][ident], xy)
# RQ-109: the 1298 bar's one move, its root's, at the canvas: 10 px above the
# bottom edge, centred (1298's 00606c10).
bar_placed_screens, bar_placements = cook_placed_bar()
assert bar_placements[1] == u(1) + u(0) + u(fe.LINEAR) + f([0.5, -512]) + u(fe.LINEAR) + f([1, -123]), \
    bar_placements[1]
assert bar_placements[:1] + bar_placements[2:] == placements[:1] + placements[2:]
BAR_PLACED_NODES = placed_nodes(bar_placed_screens)
for ident, xy in ko_rects(1024, 768, bar=True)["select"].items():
    assert BAR_PLACED_NODES["select"][ident][1][:2] == xy, (ident, BAR_PLACED_NODES["select"][ident], xy)
# RQ-125: the in-select create's moves at the canvas, the root's and its
# three panels' (Group_race's right edge by LINEAR 1, -(214 + 50)).
hall_placed_screens, hall_placements = cook_placed_1298()
assert hall_placements[2] == u(4) + u(0) + (u(fe.LINEAR) + f([0, 0])) * 2 + b"".join(
    u(i) + x + u(fe.LINEAR) + f([1, -30 - h]) for i, x, h in (
        (13, u(fe.LINEAR) + f([0, 50]), 702), (1, u(fe.LINEAR) + f([1, -264]), 704),
        (15, u(fe.LINEAR) + f([0.5, -181.5]), 72))), hall_placements[2]
assert hall_placements[:2] + hall_placements[3:] == bar_placements[:2] + bar_placements[3:]
HALL_PLACED_NODES = placed_nodes(hall_placed_screens)
for ident, xy in ko_rects(1024, 768, hall_create=True)["create"].items():
    assert HALL_PLACED_NODES["create"][ident][1][:2] == xy, (ident, HALL_PLACED_NODES["create"][ident], xy)
# Both Moradon recipes place their layouts as PLACE_SPECS does, so the loader's
# checks below (KO's placements at 1024x768, 1280x1024, 1600x1200 and
# 1281x1025) hold for each, but for the copyright line, which only the 1097
# choice places and shows as 1264 does (RQ-108); 1298's login has none
# (RQ-110, KO-FINDINGS 9.5), so its recipe hides it; and for the select, which
# in the 1298 recipe is 1298's own bar (co_CharacterSelect_us.uif, RQ-109,
# KO-FINDINGS 9.6), placed as 1298's 00606c10 places it; a move without its x
# would keep the 1024-wide x on a wider window.
PLACE_SPECS_1298 = {**PLACE_SPECS, "login": {"place": "bottom",
                                             "moves": [{"node": "Group_ServerList", "x": 0, "y": 0}]},
                    "select": BAR_PLACE_SPEC, "create": HALL_CREATE_PLACE_SPEC}
for recipe, want in (("front-end.json", PLACE_SPECS), ("front-end-1298.json", PLACE_SPECS_1298)):
    recipe_screens = json.loads((ROOT / "games/moradon" / recipe).read_text())["screens"]
    specs = {n: {k: v for k, v in recipe_screens[n].items() if k in ("place", "moves")} for n in fe.SCREENS}
    assert specs == want, (recipe, specs)
    if recipe == "front-end.json":
        assert cook_placed(specs)[1][1:] == placements[1:], recipe
    else:
        assert cook_placed_1298(specs)[1][1:] == hall_placements[1:], recipe
# The 1298 recipe binds 1298's bar as its ReceiveMessage (00607160) and info
# fill (006074c0) use it, its delete button included, and draws all of it.
select_1298 = json.loads((ROOT / "games/moradon/front-end-1298.json").read_text())["screens"]["select"]
assert select_1298["ui"] == "UI_US/co_CharacterSelect_us.uif" and select_1298["bindings"] == BAR_BINDINGS, \
    select_1298
assert not select_1298.get("hidden") and not select_1298.get("moves"), select_1298
# The 1097 choice binds the line it places to login_closed (RQ-108).
assert json.loads((ROOT / "games/moradon/front-end.json").read_text())["screens"]["login"]["bindings"][
    "Text_Rights"] == "login_closed"
# The 1298 recipe hides it and binds nothing to login_closed (RQ-110).
login_1298 = json.loads((ROOT / "games/moradon/front-end-1298.json").read_text())["screens"]["login"]
assert "Text_Rights" in login_1298["hidden"] and "login_closed" not in login_1298["bindings"].values(), login_1298
# RQ-111 (KO-FINDINGS 9.7): the 1298 recipe's message box is the one 1298's
# box manager (005282a0) loads, El_MessageBox_us.uif, its Btn_Yes and Btn_No
# bound for the select's exit, asked with row 1502 as 00607160 posts it
# (untitled).
recipe_1298 = json.loads((ROOT / "games/moradon/front-end-1298.json").read_text())
assert recipe_1298["screens"]["message"] == {
    "ui": "UI_US/el_messagebox_us.uif", "place": "centre",
    "bindings": {"Text_Message": "message", "Text_title": "title", "btn_ok": "ok", "btn_yes": "yes", "btn_no": "no"},
    "hidden": ["Edit_Common", "btn_cancel"]}, recipe_1298["screens"]["message"]
assert recipe_1298["messages"]["exit_confirm"] == {"text": {"table": "Data/Texts_us.tbl", "row": 1502}}
# RQ-115 (KO-FINDINGS 9.8): 1264's select asks the same (bt_exit, 00444e60:
# row 1502, style 4, behaviour 1) in the same box (0050c730, 0050bfb0), so the
# 1097 choice binds 1264's el_messagebox_us.uif's btn_yes and btn_no and words
# exit_confirm with the 1264 install's row 1502, untitled.
recipe_1097 = json.loads((ROOT / "games/moradon/front-end.json").read_text())
assert recipe_1097["screens"]["message"] == {
    "ui": "installer-1264:UI_US/el_messagebox_us.uif", "place": "centre",
    "bindings": {"Text_Message": "message", "Text_title": "title", "btn_ok": "ok", "btn_yes": "yes", "btn_no": "no"},
    "hidden": ["Edit_Common", "btn_cancel"]}, recipe_1097["screens"]["message"]
assert recipe_1097["messages"]["exit_confirm"] == {"text": {"table": "installer-1264:Data/Texts_us.tbl", "row": 1502}}
# RQ-116 (KO-FINDINGS 9.8): 1264's select OnKeyPress (004454e0) presses bt_exit
# for DIK_ESCAPE, so the 1097 choice's ESC asks to exit (the maintainer chose
# it, 2026-11-02); Back stays on its button. RQ-119 (KO-FINDINGS 9.9): 1298's
# bar OnKeyPress (00607810) presses no button for ESC, only skipping a playing
# path (005faad0), so the 1298 recipe's ESC does nothing otherwise (the
# maintainer chose it, 2026-11-02).
assert recipe_1097["select"]["escape"] == "exit", recipe_1097["select"]
assert recipe_1298["select"]["escape"] == "none", recipe_1298["select"]
# RQ-112 (KO-FINDINGS 9.12): 1298's Back lands on its server list (00607160
# sets the login procedure's +0x21; Init 005f68e0), so the 1298 recipe's lands
# on the realm list. RQ-123 (the maintainer, 2026-11-03: "Match 1264"): so does
# the 1097 choice's, as 1264's bt_back sets +0x35 (00445145) and its Init
# (005bd9b0) hides Group_LogIn alone, its line hidden too.
assert recipe_1298["select"]["back"] == "realms", recipe_1298["select"]
assert recipe_1097["select"]["back"] == "realms", recipe_1097["select"]
# RQ-113 (KO-FINDINGS 9.6): 1298 never hides an arrow, so the 1298 recipe
# draws both. RQ-124 (the maintainer, 2026-11-03: "Draw both, as 1264"): so
# does the 1097 choice, as 1264's select only places, compares and clicks
# bt_left and bt_right (004448f0, 00444e60, 004454e0; 9.13).
assert recipe_1298["select"]["arrows"] == "draw", recipe_1298["select"]
assert recipe_1097["select"]["arrows"] == "draw", recipe_1097["select"]
# RQ-125 (KO-FINDINGS 9.15): 1298's create is a window of its select (+0x388:
# 005fab40 loads row 2's co_characterCreate_us.uif), over the hall, so the 1298
# recipe draws it there with no char_view; the new character turned at slots
# 0-2 as 005fd120 turns it for Karus (0x406dec5d, 0x401fbb88, 0x409e0e99: 213,
# 143 and 283 degrees), the bits the client reads. 1264's create is a screen
# of its own (KO-FINDINGS 9.1), and the 1097 choice keeps it.
assert recipe_1298["select"]["create"] == "hall", recipe_1298["select"]
assert [struct.unpack("<I", struct.pack("<f", math.radians(slot["create_yaw"])))[0]
        for slot in recipe_1298["select"]["slots"]] == [0x406dec5d, 0x401fbb88, 0x409e0e99], recipe_1298["select"]
assert recipe_1298["screens"]["create"]["ui"] == "UI_US/co_characterCreate_us.uif", recipe_1298["screens"]["create"]
assert "char_view" not in recipe_1298["screens"]["create"]["bindings"].values(), recipe_1298["screens"]["create"]
assert recipe_1097["select"].get("create", "screen") == "screen", recipe_1097["select"]
assert all("create_yaw" not in slot for slot in recipe_1097["select"]["slots"]), recipe_1097["select"]
placement_problems = {
    "an unknown placement": {**PLACE_SPECS, "message": {"place": "right"}},
    "a bottom placement of another key": {**PLACE_SPECS, "message": {"place": {"bottom": 10, "x": 1}}},
    "a bottom placement of no number": {**PLACE_SPECS, "message": {"place": {"bottom": "10"}}},
    "an unknown move key": {**PLACE_SPECS, "message": {"place": "centre", "moves": [{"node": "btn_ok", "z": 1}]}},
    "two y rules": {**PLACE_SPECS, "message": {"place": "centre", "moves": [{"node": "btn_ok", "y": 1,
                                                                             "bottom": 2}]}},
    "two x rules": {**PLACE_SPECS, "message": {"place": "centre", "moves": [{"node": "btn_ok", "x": 1,
                                                                             "right": 2}]}},
    "a right of no number": {**PLACE_SPECS, "message": {"place": "centre", "moves": [{"node": "btn_ok",
                                                                                      "right": "centre"}]}},
    "a middle y": {**PLACE_SPECS, "message": {"place": "centre", "moves": [{"node": "btn_ok", "y": {"middle": 1}}]}},
    "a middle without its offset": {**PLACE_SPECS, "message": {"place": "centre", "moves": [
        {"node": "btn_ok", "x": {"ratio": 1}}]}},
    "an unknown edge": {**PLACE_SPECS, "message": {"place": "centre", "moves": [
        {"node": "btn_ok", "x": {"middle": 1, "edge": "left"}}]}},
    "an offset past its bound": {**PLACE_SPECS, "message": {"place": "centre", "moves": [
        {"node": "btn_ok", "x": 16385}]}},
    "a ratio past its bound": {**PLACE_SPECS, "message": {"place": "centre", "moves": [
        {"node": "btn_ok", "x": {"middle": 0, "ratio": 2000}}]}},
    "a value that is not a number": {**PLACE_SPECS, "message": {"place": "centre", "moves": [
        {"node": "btn_ok", "x": "left"}]}},
    "above a node no move places": {**PLACE_SPECS, "message": {"place": "centre", "moves": [
        {"node": "btn_ok", "above": ["text_msg", 4]}]}},
    "a move of no node": {**PLACE_SPECS, "message": {"place": "centre", "moves": [{"node": "btn_no", "x": 1}]}},
    "32 moves": {**PLACE_SPECS, "message": {"place": "centre", "moves": [{"node": "btn_ok", "x": 1}] * 32}},
}
for reason, specs in placement_problems.items():
    try:
        cook_placed(specs)
    except (ValueError, KeyError, TypeError) as error:
        continue
    raise AssertionError("placement cook accepted " + reason)
# A move of a hidden node is not written.
hidden = cook_placed({**PLACE_SPECS, "loading": {**PLACE_SPECS["loading"], "hidden": ["Text_Version"]}})[1]
assert hidden[3] == u(1) + u(0) + u(fe.LINEAR) + f([0.5, -339]) + u(fe.LINEAR) + f([0.5, -216.5]), hidden[3]
print("PASS front-end placement cook: KO's placements at the canvas, the 1097 and 1298 recipes' the same "
      "but for the 1097 choice's copyright line and 1298's own select bar and in-select create, %d refusals"
      % len(placement_problems))
# --- create's slide (version 20, RQ-126) ----------------------------------------

# KO-FINDINGS 9.15: 1298's create slides its panels in each time it opens
# (SetVisible 00606650 zeroes d; Tick 00606450 adds max(t 1300 (w - d) / w, 2)
# a frame, w Group_race's width): Group_race from x = W (Load 00603850) to
# W - w - 50, its arrival ending the slide; Group_class from x = -w_c by
# trunc(d) to 50; Group_name from y = H by trunc((h + 30) d / (w_c + 50)) to
# H - 30 - h. As front-end-1298.json says it.
HALL_CREATE_SLIDE = {"rate": 1300, "floor": 2, "nodes": [
    {"node": "Group_race", "from": "right"}, {"node": "Group_class", "from": "left"},
    {"node": "Group_name", "from": "bottom", "with": "Group_class"}]}
assert recipe_1298["screens"]["create"]["slide"] == HALL_CREATE_SLIDE, recipe_1298["screens"]["create"]
assert "slide" not in recipe_1097["screens"]["create"], recipe_1097["screens"]["create"]
HALL_SLIDE_SPECS = {**PLACE_SPECS, "select": BAR_PLACE_SPEC,
                    "create": {**HALL_CREATE_PLACE_SPEC, "slide": HALL_CREATE_SLIDE}}
hall_slides = []
assert cook_placed_1298(HALL_SLIDE_SPECS, hall_slides)[1] == hall_placements
# The lead Group_race (node 1) on x from W (LINEAR 1, 0); Group_class (13) on
# x from -216 (its width); Group_name (15) on y from H, by 102 / 266: its
# travel at the canvas (768 - 666) over Group_class's (50 + 216).
HALL_SLIDE_RECORD = u(3) + f([1300, 2]) + u(1) + u(0) + u(fe.LINEAR) + f([1, 0]) + f([1, 1]) + \
    u(13) + u(0) + u(fe.LINEAR) + f([0, -216]) + f([1, 1]) + u(15) + u(1) + u(fe.LINEAR) + f([1, 0]) + f([102, 266])
assert hall_slides == [HALL_SLIDE_RECORD], hall_slides
# No slide: a count of 0.
plain_slides = []
cook_placed_1298(slides=plain_slides)
assert plain_slides == [u(0)], plain_slides


def slid(**change):
    return {**HALL_SLIDE_SPECS, "create": {**HALL_SLIDE_SPECS["create"], "slide": {**HALL_CREATE_SLIDE, **change}}}


def slid_node(i, **change):
    nodes = [dict(n) for n in HALL_CREATE_SLIDE["nodes"]]
    nodes[i].update(change)
    return slid(nodes=nodes)


slide_problems = {
    "a slide off create": {**HALL_SLIDE_SPECS, "message": {**PLACE_SPECS["message"], "slide": HALL_CREATE_SLIDE}},
    "a slide that is not an object": {**HALL_SLIDE_SPECS, "create": {**HALL_CREATE_PLACE_SPEC, "slide": []}},
    "a slide without its floor": {**HALL_SLIDE_SPECS, "create": {**HALL_CREATE_PLACE_SPEC, "slide": {
        "rate": 1300, "nodes": HALL_CREATE_SLIDE["nodes"]}}},
    "an unknown slide key": slid(speed=1),
    "a rate of 0": slid(rate=0),
    "a rate past its bound": slid(rate=100001),
    "a rate that is not a number": slid(rate="1300"),
    "a floor of 0": slid(floor=0),
    # Under the float step just below 10^6 a float d can stop growing (d +
    # floor rounding back to d) and the slide never ends.
    "a floor under 1/16": slid(floor=0.0624),
    "a floor past its bound": slid(floor=1025),
    "a floor that is infinite": slid(floor=math.inf),
    "no nodes": slid(nodes=[]),
    "nine nodes": slid(nodes=[{"node": "Group_race", "from": "right"}] * 9),
    "a node twice": slid(nodes=[{"node": "Group_race", "from": "right"}, {"node": "Group_race", "from": "left"}]),
    "an unknown edge": slid_node(0, **{"from": "front"}),
    "a node without its edge": slid(nodes=[{"node": "Group_race"}]),
    "an unknown node key": slid_node(1, speed=2),
    "a node the layout lacks": slid_node(1, node="Group_nation"),
    "a with of itself": slid_node(2, **{"with": "Group_name"}),
    "a with of a node not sliding": slid_node(2, **{"with": "edit_name"}),
    "a with of no travel": {**HALL_SLIDE_SPECS, "create": {**HALL_CREATE_PLACE_SPEC, "moves": [
        {"node": "Group_class", "x": -216, "bottom": 30}] + HALL_CREATE_PLACE_SPEC["moves"][1:],
        "slide": HALL_CREATE_SLIDE}},
    "a hidden node": {**HALL_SLIDE_SPECS, "create": {**HALL_SLIDE_SPECS["create"], "hidden": ["Group_class"]}},
}
for reason, specs in slide_problems.items():
    try:
        cook_placed_1298(specs, [])
    except (ValueError, KeyError, TypeError) as error:
        continue
    raise AssertionError("slide cook accepted " + reason)
print("PASS front-end slide cook: the 1298 recipe's create slide as 1298's Load and Tick move its panels, "
      "none for the 1097 choice, %d refusals" % len(slide_problems))


def ko_slide(width, height, dt):
    """1298's Tick (00606450) at a window, from the open (SetVisible 00606650,
    d = 0) to the frame it clears its flag, as the binary reads: d (a float,
    +0xb8) += max(dt 1300 (w - d) / w, 2), w Group_race's width 214; Group_race
    at max(W - trunc(d), W - w - 50), clearing the flag there; Group_class at
    min(trunc(d) - w_c, 50), w_c 216; Group_name at max(H - trunc((h + 30) d /
    (w_c + 50)), H - 30 - h), h 72; each keeping its other coordinate (Load
    00603850's: Group_name's x (W - w) / 2, the others' y H - 30 - h). Each
    frame's (race, class, name) top-lefts, the first the open's (Load's)."""
    def f32(x):
        return struct.unpack("<f", struct.pack("<f", x))[0]
    race_y, class_y, name_x = height - 30 - 704, height - 30 - 702, (width - 363) // 2

    def at(d):
        race = max(width - math.trunc(d), width - 214 - 50)
        return (race, race_y, min(math.trunc(d) - 216, 50), class_y, name_x,
                max(height - math.trunc(102 * d / 266), height - 30 - 72)), race == width - 214 - 50
    d, frames = 0.0, [at(0.0)[0]]
    while True:
        d = f32(d + max(dt * 1300 * (214 - d) / 214, 2.0))
        place, done = at(d)
        frames.append(place)
        if done:
            return frames


# 1298's slide ends 1 or 2 px short of Group_class's 50 and 1 px below
# Group_name's H - 30 - h at frame rates whose last steps are the 2 px floor:
# the flag clears on the frame d reaches 264, Group_race's travel, while
# Group_class's is 266.
for dt, frames, final in ((1 / 30, 44, (760, 34, 48, 36, 330, 667)), (1 / 60, 58, (760, 34, 49, 36, 330, 667)),
                          (1 / 144, 84, (760, 34, 48, 36, 330, 667)), (0.25, 1, (760, 34, 50, 36, 330, 666))):
    run = ko_slide(1024, 768, dt)
    assert (len(run) - 1, run[-1]) == (frames, final), (dt, len(run) - 1, run[-1])
PLACEMENT_OK = u(0) + b"".join(placements) + u(0)
SIZES = ((1024, 768), (1280, 1024), (1600, 1200), (1281, 1025), (800, 600))


def moves_raw(*moves, flags=0, layout=4, logo=u(0)):
    """A placement of no moves but `moves` ((node, (kind, a, c), (kind, a, c)))
    on layout `layout`."""
    lists = [u(0)] * 5
    lists[layout] = u(len(moves)) + b"".join(u(n) + u(x[0]) + f(x[1:]) + u(y[0]) + f(y[1:]) for n, x, y in moves)
    return u(flags) + b"".join(lists) + logo


NAN = struct.unpack("<f", struct.pack("<I", 0x7FC00000))[0]
PLACEMENT_CASES = {
    "ok-placed": blob(screen_data=placed_screens, placement=PLACEMENT_OK),
    "ok-placed-scaled": blob(screen_data=placed_screens, placement=u(1) + PLACEMENT_OK[4:]),
    "ok-placed-bar": blob(screen_data=bar_placed_screens, placement=u(0) + b"".join(bar_placements) + u(0)),
    "ok-placed-1298": blob(screen_data=hall_placed_screens, placement=u(0) + b"".join(hall_placements) + u(0),
                           create=1, slide=HALL_SLIDE_RECORD),
    "ok-placement-keep": blob(placement=moves_raw((1, (fe.KEEP, 0, 0), (fe.KEEP, 0, 0)))),
    "bad-placement-flags": blob(placement=u(2) + NO_PLACEMENT[4:]),
    "bad-placement-missing": blob(placement=b""),
    "bad-placement-truncated": blob(screen_data=placed_screens, placement=PLACEMENT_OK[:-4]),
    "bad-move-node": blob(placement=moves_raw((8, (fe.LINEAR, 0, 0), (fe.LINEAR, 0, 0)))),
    "bad-move-kind": blob(placement=moves_raw((0, (3, 0, 0), (fe.LINEAR, 0, 0)))),
    "bad-move-nan": blob(placement=moves_raw((0, (fe.LINEAR, NAN, 0), (fe.LINEAR, 0, 0)))),
    "bad-move-scale": blob(placement=moves_raw((0, (fe.LINEAR, 4.5, 0), (fe.LINEAR, 0, 0)))),
    "bad-move-offset": blob(placement=moves_raw((0, (fe.LINEAR, 0, 16385), (fe.LINEAR, 0, 0)))),
    "bad-move-keep-values": blob(placement=moves_raw((1, (fe.KEEP, 1, 0), (fe.KEEP, 0, 0)))),
    # A move that puts a node elsewhere at the canvas than the file does.
    "bad-move-off-canvas": blob(placement=moves_raw((0, (fe.LINEAR, 0, 5), (fe.LINEAR, 0, 0)))),
    "bad-moves-33": blob(placement=moves_raw(*[(0, (fe.LINEAR, 0, 0), (fe.LINEAR, 0, 0))] * 33)),
    "bad-logo-moves-without-logo": blob(placement=moves_raw(logo=u(1) + u(0) + (u(fe.LINEAR) + f([0, 0])) * 2)),
    "ok-logo-moves": blob(music=ONE_TRACK, logo=LOGO_OK,
                          placement=moves_raw(logo=u(1) + u(0) + (u(fe.LINEAR) + f([0.5, -16])) +
                                              (u(fe.LINEAR) + f([0.5, -8])))),
}


# RQ-126 (version 20): create's slide, on the 1298 layouts; a record with
# `change` (offset: bytes) patched in.
def slide_raw(*patches, record=HALL_SLIDE_RECORD):
    for at, data in patches:
        record = record[:at] + data + record[at + len(data):]
    return blob(screen_data=hall_placed_screens, placement=u(0) + b"".join(hall_placements) + u(0), create=1,
                slide=record)


SLIDE_NODE = 12  # the first node record's offset (after the count, rate and floor)
SLIDE_CASES = {
    "bad-version-19": blob(version=19),
    "ok-slide-screen": blob(slide=u(1) + f([1300, 2]) + u(0) + u(0) + u(fe.LINEAR) + f([1, 0]) + f([1, 1])),
    "bad-slide-missing": blob(placement=NO_PLACEMENT, slide=b""),
    "bad-slide-truncated": slide_raw(record=HALL_SLIDE_RECORD[:-4]),
    "bad-slide-nodes-9": slide_raw(record=u(9) + HALL_SLIDE_RECORD[4:]),
    "bad-slide-rate": slide_raw((4, f([0]))),
    "bad-slide-rate-high": slide_raw((4, f([100001]))),
    "bad-slide-floor": slide_raw((8, f([0]))),
    "bad-slide-floor-nan": slide_raw((8, f([NAN]))),
    "bad-slide-floor-small": slide_raw((8, f([1e-5]))),
    "bad-slide-floor-under": slide_raw((8, f([0.0624]))),
    "ok-slide-floor-least": slide_raw((8, f([1 / 16]))),
    "bad-slide-node": slide_raw((SLIDE_NODE, u(99))),
    "bad-slide-node-twice": slide_raw((SLIDE_NODE + 28, u(1))),
    "bad-slide-axis": slide_raw((SLIDE_NODE + 4, u(2))),
    "bad-slide-start-keep": slide_raw((SLIDE_NODE + 8, u(fe.KEEP))),
    "bad-slide-start-offset": slide_raw((SLIDE_NODE + 16, f([16385]))),
    "bad-slide-num": slide_raw((SLIDE_NODE + 20, f([0]))),
    "bad-slide-den-high": slide_raw((SLIDE_NODE + 24, f([16385]))),
}


# RQ-125: the synthetic screens with a create that binds no char_view (a
# create over the hall).
VIEWLESS_SCREENS = screens[:2] + [hall_create] + screens[3:]


# KO's login bar has no status line: a login screen without `notice` cooks
# and loads.
plain = {n: spec(n) for n in fe.SCREENS}
plain["login"]["bindings"].pop("notice")
valid = blob()


# RQ-108 (version 12): a login screen node bound to login_closed (KO's
# copyright line, drawn only while the login group is not); the loader
# refuses one on another screen (cooked here without the cook's own check).
def rights(screen):
    trees = {n + ".uif": TREES[n]()[1] for n in fe.SCREENS}
    root = {"login": lambda: node(0, "root", [
                node(0, "Group_LogIn", [button("Btn_Login"), button("Btn_Cancel"), text("notice")]),
                node(0, "Group_ServerList", [node(14, "List_Server"), button("Btn_Connect")]), text("rights")]),
            "select": lambda: node(0, "root", [button("bt_left"), button("bt_right"), button("bt_back"),
                                               button("bt_exit"), text("text00"), text("rights")])}[screen]
    trees[screen + ".uif"] = root()[1]
    specs = {n: spec(n) for n in fe.SCREENS}
    specs[screen]["bindings"]["rights"] = "login_closed"
    saved = dict(fe.ONLY_ON)
    fe.ONLY_ON.clear()
    try:
        return cook_screens(trees=trees, specs=specs)[0]
    finally:
        fe.ONLY_ON.update(saved)


# RQ-109 (version 13): screens the cook refuses, cooked without its checks
# for the loader's own: a bar action on the login, and a select of no info text.
def bar_off_select():
    specs = {n: spec(n) for n in fe.SCREENS}
    specs["login"]["bindings"]["notice"] = "select_start"
    saved = dict(fe.ONLY_ON)
    fe.ONLY_ON.clear()
    try:
        return cook_screens(specs=specs)[0]
    finally:
        fe.ONLY_ON.update(saved)


def no_info():
    saved = set(fe.INFO_TEXTS)
    fe.INFO_TEXTS.add("exit")
    try:
        return cook_screens(specs={**{n: spec(n) for n in fe.SCREENS}, "select": spec("select", hidden=["text00"])})[0]
    finally:
        fe.INFO_TEXTS.clear()
        fe.INFO_TEXTS.update(saved)


# RQ-130 (version 21): create's race and class choices; node `ident` of
# screen `index` with its action or flags patched (unchecked).
def patch_node(screen_data, index, ident, action=None, flags=None):
    data = bytearray(screen_data[index])
    at = 4
    for _ in range(struct.unpack_from("<I", data)[0]):
        length = struct.unpack_from("<I", data, at + 24)[0]
        if data[at + 28:at + 28 + length] == ident.encode():
            if action is not None:
                struct.pack_into("<I", data, at + 28 + length, action)
            if flags is not None:
                struct.pack_into("<I", data, at + 32 + length, flags)
            return screen_data[:index] + [bytes(data)] + screen_data[index + 1:]
        at = fe.node_end(bytes(data), at)
    raise AssertionError("no node " + ident)


def choice_record(races, classes):
    """Create's choice section (item 14) from (node id, race, default) and
    (node id, specialties, image id or None, label ids) entries, node ids of
    CHOICE's create screen (unchecked)."""
    at = {i: k for k, (i, _, _) in enumerate(node_records(CHOICE[2]))}
    data = u(len(races)) + b"".join(u(at[n]) + u(r) + u(d) for n, r, d in races) + u(len(classes))
    for n, codes, image, labels in classes:
        data += u(at[n]) + u(len(codes)) + b"".join(u(c) for c in codes) + \
            u(0xFFFFFFFF if image is None else at[image]) + u(len(labels)) + b"".join(u(at[x]) for x in labels)
    return data


RACE_TU = ("btn_race_ka_tu", 2, 102)
WARRIOR = ("btn_class_warrior", [101, 201], "img_warrior", ["str_01"])
PRIEST = ("btn_class_priest", [104, 204], "img_priest", ["str_01", "int_01"])
assert choice_record([RACE_TU], [WARRIOR, PRIEST]) == CHOSEN["data"]
CHOICE_SECTIONS = {
    "race-node": ([("btn_class_warrior", 2, 102)], [WARRIOR, PRIEST]),
    "race-unbound": ([RACE_TU, ("btn_race_ka_wt", 3, 103)], [WARRIOR, PRIEST]),
    "race-0": ([("btn_race_ka_tu", 0, 102)], [WARRIOR, PRIEST]),
    "race-65536": ([("btn_race_ka_tu", 65536, 102)], [WARRIOR, PRIEST]),
    "race-default-0": ([("btn_race_ka_tu", 2, 0)], [WARRIOR, PRIEST]),
    "race-twice": ([RACE_TU, RACE_TU], [WARRIOR, PRIEST]),
    "race-missing": ([], [WARRIOR, PRIEST]),
    "class-node": ([RACE_TU], [WARRIOR, ("btn_race_ka_tu", [104], None, [])]),
    "class-twice": ([RACE_TU], [WARRIOR, PRIEST, PRIEST]),
    "class-missing": ([RACE_TU], [PRIEST]),
    "class-no-specialty": ([RACE_TU], [WARRIOR, ("btn_class_priest", [], None, ["int_01"])]),
    "class-17-specialties": ([RACE_TU], [WARRIOR, ("btn_class_priest", list(range(300, 317)), None, ["int_01"])]),
    "class-specialty-shared": ([RACE_TU], [WARRIOR, ("btn_class_priest", [104, 201], "img_priest", ["int_01"])]),
    "class-specialty-0": ([RACE_TU], [WARRIOR, ("btn_class_priest", [0], "img_priest", ["int_01"])]),
    "class-image-text": ([RACE_TU], [WARRIOR, ("btn_class_priest", [104], "str_02", ["int_01"])]),
    "class-image-twice": ([RACE_TU], [WARRIOR, ("btn_class_priest", [104], "img_warrior", ["int_01"])]),
    "class-label-unflagged": ([RACE_TU], [WARRIOR, ("btn_class_priest", [104], "img_priest", ["str_02", "int_01"])]),
    "class-label-twice": ([RACE_TU], [WARRIOR, ("btn_class_priest", [104], "img_priest", ["int_01", "int_01"])]),
    "class-label-unnamed": ([RACE_TU], [WARRIOR, ("btn_class_priest", [104], "img_priest", [])]),
}


CHOICE_CASES = {
    # RQ-158 (version 24): a create model per race.
    "bad-version-23": blob(version=23),
    "ok-create-races": blob(creates=u(3) + u(2) + character() + u(3) + character() + u(13) + character()),
    "ok-create-races-32": blob(creates=u(32) + b"".join(u(r) + character() for r in range(1, 33))),
    "bad-create-races-0": blob(creates=u(0)),
    "bad-create-races-33": blob(creates=u(33) + b"".join(u(r) + character() for r in range(1, 34))),
    "bad-create-race-0": blob(creates=u(1) + u(0) + character()),
    "bad-create-race-65536": blob(creates=u(1) + u(65536) + character()),
    "bad-create-race-twice": blob(creates=u(2) + u(2) + character() + u(2) + character()),
    "bad-create-races-truncated": blob(creates=u(2) + u(2) + character() + u(3)),
    "bad-version-20": blob(version=20),
    "bad-version-21": blob(version=21),
    "bad-version-22": blob(version=22),
    # RQ-172 (version 25): create's race and class buttons by KO's codes, with
    # create's choice section (item 14).
    "bad-version-24": blob(version=24),
    "ok-create-choice": blob(screen_data=CHOICE, choices=CHOSEN["data"]),
    "ok-create-choice-chosen": blob(screen_data=choice_screens(states={"btn_race_ka_tu": "down",
                                                                       "btn_class_priest": "down"}),
                                    choices=CHOSEN["data"]),
    "ok-create-choice-shown": blob(screen_data=choice_screens(class_labels="show"), choices=CHOSEN["data"]),
    "ok-create-choice-race-only": blob(screen_data=choice_cook(classes={}, class_labels=None)[0],
                                       choices=choice_cook(classes={}, class_labels=None)[1]["data"]),
    "bad-create-choice-unlisted": blob(screen_data=CHOICE),
    "bad-create-choice-two-chosen": blob(screen_data=patch_node(patch_node(CHOICE, 2, "btn_class_priest", flags=1), 2,
                                                                "btn_class_warrior", flags=1),
                                         choices=CHOSEN["data"]),
    "bad-create-choice-disabled": blob(screen_data=patch_node(CHOICE, 2, "btn_class_priest", flags=2),
                                       choices=CHOSEN["data"]),
    "bad-create-choice-text": blob(screen_data=patch_node(CHOICE, 2, "text_desc",
                                                          action=fe.ACTIONS.index("create_class")),
                                   choices=CHOSEN["data"]),
    "bad-create-choice-off-create": blob(screen_data=patch_node(bar_screens, 1, "btn_delete",
                                                                action=fe.ACTIONS.index("create_race"))),
    "bad-node-flags-8": blob(screen_data=patch_node(CHOICE, 2, "img_warrior", flags=8), choices=CHOSEN["data"]),
    "bad-node-flags-64": blob(screen_data=patch_node(CHOICE, 2, "img_warrior", flags=64), choices=CHOSEN["data"]),
    "bad-class-label-off-create": blob(screen_data=patch_node(CHOICE, 0, "notice", flags=16),
                                       choices=CHOSEN["data"]),
    "bad-class-label-both": blob(screen_data=patch_node(CHOICE, 2, "str_01", flags=48), choices=CHOSEN["data"]),
    "bad-class-label-unlisted": blob(screen_data=patch_node(CHOICE, 2, "str_02", flags=16), choices=CHOSEN["data"]),
    "bad-class-label-mixed": blob(screen_data=patch_node(CHOICE, 2, "int_01", flags=32), choices=CHOSEN["data"]),
    **{"bad-choice-" + reason: blob(screen_data=CHOICE, choices=choice_record(*entries))
       for reason, entries in CHOICE_SECTIONS.items()},
    "bad-choice-truncated": blob(screen_data=CHOICE, choices=CHOSEN["data"][:-4]),
}
cases = {
    "ok-no-notice": blob(screen_data=cook_screens(specs=plain)[0]),
    # RQ-130 (version 21): create's race and class choices.
    **CHOICE_CASES,
    "ok-valid": valid,
    "ok-three-slots": blob(slots=3),
    "ok-plug": blob(plug=0),
    "bad-truncated": valid[:-1],
    "bad-trailing": valid + b"\0",
    "bad-magic": blob(magic=b"N3FX"),
    "bad-version": blob(version=4),
    # RQ-086 (version 6): the select hall's front-clip mode, 0 hover or 1 loop.
    "bad-version-5": blob(version=5),
    "ok-front-clip-loop": blob(front_clip=1),
    "bad-front-clip": blob(front_clip=2),
    "bad-front-clip-missing": blob(front_clip=None),
    # RQ-087 (version 7): the turn mode, 0 rotate or 1 path, the path mode's
    # camera paths, and a hall of no parts.
    "bad-version-6": blob(version=6),
    "ok-no-hall": blob(hall=0),
    "ok-turn-path": blob(turn=1),
    "ok-turn-path-three-slots": blob(slots=3, turn=1),
    "ok-turn-path-extra": blob(slots=3, turn=1, paths=u(6) + PATHS3 + path(1, 2)),
    "ok-turn-path-rates": blob(turn=1, paths=u(1) + path(eye_rate=15.0, at_rate=1000.0)),
    "bad-turn-mode": blob(turn=2),
    "bad-turn-rotate-paths": blob(turn=0, paths=u(1) + path()),
    "bad-turn-path-none": blob(turn=1, paths=u(0)),
    "bad-turn-path-nine": blob(slots=3, turn=1, paths=u(9) + PATHS3 + path(1, 2) * 4),
    "bad-path-no-entry": blob(slots=3, turn=1, paths=u(4) + PATHS3[len(path()):]),
    "bad-path-no-way-back": blob(slots=3, turn=1, paths=u(4) + PATHS3[:-len(path(2, 0))]),
    "bad-path-twice": blob(slots=3, turn=1, paths=u(6) + PATHS3 + path(0, 1)),
    "bad-path-entry-to-1": blob(slots=3, turn=1, paths=u(6) + PATHS3 + path(fe.ENTRY, 1)),
    "bad-path-own-slot": blob(slots=3, turn=1, paths=u(6) + PATHS3 + path(1, 1)),
    "bad-path-slot": blob(turn=1, paths=u(2) + path() + path(0, 1)),
    "bad-path-rate": blob(turn=1, paths=u(1) + path(eye_rate=0.0)),
    "bad-path-rate-high": blob(turn=1, paths=u(1) + path(at_rate=1001.0)),
    "bad-path-keys": blob(turn=1, paths=u(1) + path(eye=())),
    "bad-path-truncated": blob(turn=1, paths=u(1) + path()[:-4]),
    # RQ-095 (version 8): up to 256 textures, the zone the hall draws (no hall
    # with it; each mesh UNLIT or lit, and CUT_ZERO or BLEND, with its sort
    # point) and the camera's fog (on, colour, start, end within the far).
    "bad-version-7": blob(version=7),
    # RQ-101 (version 9): the logo screen, absent (0) or its nodes, groups,
    # music and flags.
    "bad-version-8": blob(version=8),
    **LOGO_CASES,
    # RQ-102 (version 10): each message's title and wording.
    "bad-version-9": blob(version=9),
    **MESSAGE_CASES,
    # RQ-106 (version 11): the placement.
    "bad-version-10": blob(version=10),
    **PLACEMENT_CASES,
    # RQ-126 (version 20): create's slide.
    **SLIDE_CASES,
    # RQ-108 (version 12): the action login_closed, on the login screen only.
    "bad-version-11": blob(version=11),
    "ok-login-closed": blob(screen_data=rights("login")),
    "bad-login-closed-off-login": blob(screen_data=rights("select")),
    # RQ-109 (version 13): 1298's select bar, its info texts in place of
    # char_info; its actions on the select only, and an info text there.
    "bad-version-12": blob(version=12),
    # RQ-111 (version 14): the message box's yes and no, and exit_confirm.
    "bad-version-13": blob(version=13),
    # RQ-116 (version 15): what ESC presses on the select, 0 back or 1 exit.
    "bad-version-14": blob(version=14),
    "ok-select-escape-exit": blob(escape=1),
    # RQ-119 (version 16): or 2 none.
    "bad-version-15": blob(version=15),
    "ok-select-escape-none": blob(escape=2),
    "bad-select-escape": blob(escape=3),
    "bad-select-escape-missing": blob(escape=None),
    # RQ-112 (version 17): where the select's Back lands, 0 login or 1 realms.
    "bad-version-16": blob(version=16),
    "ok-select-back-realms": blob(back=1),
    "bad-select-back": blob(back=2),
    "bad-select-back-missing": blob(back=None),
    # RQ-113 (version 18): the end-of-row arrow, 0 hidden or 1 drawn.
    "bad-version-17": blob(version=17),
    "ok-select-arrows-draw": blob(arrows=1),
    "bad-select-arrows": blob(arrows=2),
    "bad-select-arrows-missing": blob(arrows=None),
    # RQ-125 (version 19): where create draws, 0 its own screen (char_view
    # bound) or 1 over the hall (none), then over the hall each slot's create
    # yaw, finite and within a turn.
    "bad-version-18": blob(version=18),
    "ok-create-hall": blob(create=1, screen_data=VIEWLESS_SCREENS),
    "ok-create-hall-3": blob(slots=3, create=1, create_yaws=[-3.71755147, -2.49582100, -4.93928194],
                             screen_data=VIEWLESS_SCREENS),
    "bad-create-mode": blob(create=2),
    "bad-create-missing": blob(create=None),
    "bad-create-hall-view": blob(create=1),
    "bad-create-screen-no-view": blob(screen_data=VIEWLESS_SCREENS),
    "bad-create-yaw": blob(create=1, create_yaws=[7.0], screen_data=VIEWLESS_SCREENS),
    "bad-create-yaw-nan": blob(create=1, create_yaws=[NAN], screen_data=VIEWLESS_SCREENS),
    "bad-create-yaws-missing": blob(create=1, create_yaws=[], screen_data=VIEWLESS_SCREENS),
    "ok-select-bar": blob(screen_data=bar_screens),
    "ok-select-bar-name": blob(screen_data=bar(("str_id",))),
    "bad-select-bar-off-select": blob(screen_data=bar_off_select()),
    "bad-select-no-info": blob(screen_data=no_info()),
    "ok-textures-256": blob(more_textures=256 - len(textures.list) - 1),
    "bad-textures-257": blob(more_textures=257 - len(textures.list) - 1),
    "ok-zone": blob(hall=0, zone=u(3) + zone_mesh() + zone_mesh(fe.CUT_ZERO | fe.UNLIT) +
                    zone_mesh(fe.BLEND | fe.UNLIT, (0, 3, 9))),
    "ok-zone-fog": blob(hall=0, zone=u(1) + zone_mesh(fe.BLEND), fog=u(1) + f([1, 1, 1, 3.2, 32])),
    "ok-fog-no-zone": blob(fog=u(1) + f([0.5, 0.25, 0, 0, 1])),
    "bad-zone-and-hall": blob(hall=1, zone=u(1) + zone_mesh()),
    "bad-zone-flags-none": blob(hall=0, zone=u(1) + zone_mesh(0)),
    "bad-zone-flags-unlit": blob(hall=0, zone=u(1) + zone_mesh(fe.UNLIT)),
    "bad-zone-flags-both": blob(hall=0, zone=u(1) + zone_mesh(fe.CUT_ZERO | fe.BLEND)),
    "bad-zone-flags-alpha-test": blob(hall=0, zone=u(1) + zone_mesh(fe.CUT_ZERO | fe.ALPHA_TEST)),
    "bad-zone-flags-double": blob(hall=0, zone=u(1) + zone_mesh(fe.BLEND | fe.DOUBLE_SIDED)),
    "bad-zone-meshes": blob(hall=0, zone=u(257) + zone_mesh() * 257),
    "bad-zone-truncated": truncated_zone(),
    "ok-zone-totals": blob(hall=0, zone=u(3) + MAX_INDEX_MESH * 3),
    "bad-zone-totals": blob(hall=0, zone=u(4) + MAX_INDEX_MESH * 3 + zone_mesh()),
    "ok-zone-vertex-totals": blob(hall=0, zone=u(3) + MAX_VERTEX_MESH * 3),
    "bad-zone-vertex-totals": blob(hall=0, zone=u(4) + MAX_VERTEX_MESH * 3 + zone_mesh()),
    "bad-hall-zone-flags": blob(hall=1).replace(MESH, MESH[:4] + u(fe.CUT_ZERO) + MESH[8:], 1),
    "bad-fog-flag": blob(fog=u(2) + f([1, 1, 1, 3, 32])),
    "bad-fog-empty": blob(fog=u(1) + f([1, 1, 1, 10, 10])),
    "bad-fog-past-far": blob(fog=u(1) + f([1, 1, 1, 3, 33])),
    "bad-fog-negative": blob(fog=u(1) + f([1, 1, 1, -1, 32])),
    "bad-fog-colour": blob(fog=u(1) + f([1.5, 1, 1, 3, 32])),
    "bad-fog-off-values": blob(fog=u(0) + f([1, 0, 0, 0, 0])),
    "bad-clip-blend": blob(blends=[-0.1]),
    "bad-clip-blend-nan": blob(blends=[float("nan")]),
    "bad-spot-rate": blob(spot_rate=0),
    "bad-select-clips": blob(select_clips=2),
    "ok-music": blob(music=u(1) + track() + u(0) * 3 + u(fe.NO_MUSIC)),
    "ok-music-two": blob(music=u(2) + track() + track(loop=0) + u(0) + u(1) + u(fe.NO_MUSIC) * 2),
    "bad-music-tracks": blob(music=u(5) + track() * 5 + u(fe.NO_MUSIC) * 4),
    "bad-music-loop": blob(music=u(1) + track(loop=2) + u(fe.NO_MUSIC) * 4),
    "bad-music-channels": blob(music=u(1) + track(channels=2) + u(fe.NO_MUSIC) * 4),
    "bad-music-rate": blob(music=u(1) + track(rate=44100) + u(fe.NO_MUSIC) * 4),
    "bad-music-frame-count": blob(music=u(1) + track(frames=11) + u(fe.NO_MUSIC) * 4),
    "bad-music-layer": blob(music=u(1) + track(mp3_frame(layer=2) + TRACK[96:]) + u(fe.NO_MUSIC) * 4),
    "bad-music-cut-frame": blob(music=u(1) + track(TRACK[:-1], frames=10) + u(fe.NO_MUSIC) * 4),
    "bad-music-empty": blob(music=u(1) + track(b"", frames=1) + u(fe.NO_MUSIC) * 4),
    "bad-music-screen": blob(music=u(1) + track() + u(1) + u(fe.NO_MUSIC) * 3),
    "bad-music-missing": valid[:-len(NO_MUSIC) - 4],
    # RQ-083 (version 5): PCM tracks and restart periods.
    "ok-music-pcm": blob(music=u(2) + pcm_track(loop=0, restart=21.66) + pcm_track() + u(0) + u(1) * 2 +
                        u(fe.NO_MUSIC)),
    "ok-music-pcm-mono": blob(music=u(1) + pcm_track(PCM[:100], rate=8000, channels=1) + u(0) + u(fe.NO_MUSIC) * 3),
    "ok-music-mpeg-restart": blob(music=u(1) + track(restart=3600.0) + u(0) + u(fe.NO_MUSIC) * 3),
    "bad-music-kind": blob(music=u(1) + pcm_track(kind=2) + u(fe.NO_MUSIC) * 4),
    "bad-music-pcm-rate": blob(music=u(1) + pcm_track(rate=96001) + u(fe.NO_MUSIC) * 4),
    "bad-music-pcm-rate-low": blob(music=u(1) + pcm_track(rate=7999) + u(fe.NO_MUSIC) * 4),
    "bad-music-pcm-channels": blob(music=u(1) + pcm_track(channels=3, frames=100) + u(fe.NO_MUSIC) * 4),
    "bad-music-pcm-frames": blob(music=u(1) + pcm_track(frames=99) + u(fe.NO_MUSIC) * 4),
    "bad-music-pcm-odd": blob(music=u(1) + pcm_track(PCM[:-1], frames=100) + u(fe.NO_MUSIC) * 4),
    "bad-music-pcm-empty": blob(music=u(1) + pcm_track(b"", frames=0) + u(fe.NO_MUSIC) * 4),
    "bad-music-pcm-as-mpeg": blob(music=u(1) + track(PCM, rate=22050, channels=2, frames=100) + u(fe.NO_MUSIC) * 4),
    "bad-music-restart-low": blob(music=u(1) + pcm_track(restart=0.05) + u(fe.NO_MUSIC) * 4),
    "bad-music-restart-high": blob(music=u(1) + pcm_track(restart=3601.0) + u(fe.NO_MUSIC) * 4),
    "bad-music-restart-negative": blob(music=u(1) + pcm_track(restart=-21.66) + u(fe.NO_MUSIC) * 4),
    "bad-music-restart-nan": blob(music=u(1) + pcm_track(restart=0x7FC00000) + u(fe.NO_MUSIC) * 4),
    "bad-slots": blob(slots=4),
    "bad-slot-count": blob(slot_count=2),
    "bad-canvas": blob(canvas=(800, 600)),
    "bad-unknown-action": blob(screen_data=patched_action(screens, 0, 99)),
    "bad-action-twice": blob(screen_data=patched_action(screens, 0, fe.ACTIONS.index("login"))),
    "bad-unbound-action": blob(screen_data=unbound("loading", "progress")),
    "bad-font-texture": blob(font_index=0),
    "bad-light-range": blob(light=dict(LIGHT, range=2e8)),
    "bad-light-attenuation": blob(light=dict(LIGHT, attenuation=[0, 0, 0])),
    "bad-plug-joint": blob(plug=999),
    "bad-string": blob(strings=["\x01"] * 6),
}
work = pathlib.Path(tempfile.mkdtemp(prefix="n3e-front-end-"))
try:
    args = []
    for name, data in cases.items():
        (work / name).mkdir()
        (work / name / "front-end.bin").write_bytes(data)
        args += [name.split("-")[0], str(work / name)]
    run = subprocess.run([str(ROOT / "build/client/n3e-front-end-check"), *args], capture_output=True, text=True)
    sys.stdout.write("".join(l for l in run.stdout.splitlines(True) if not l.startswith(("placed ", "slide "))))
    assert run.returncode == 0, run.stdout + run.stderr
    # RQ-095: the zone's refusals, each for its own reason.
    for name, reason in (("bad-zone-totals", "front end zone totals"),
                         ("bad-zone-vertex-totals", "front end zone totals"), ("bad-zone-meshes", "count"),
                         ("bad-zone-and-hall", "front end hall and zone")):
        line = next(l for l in run.stdout.splitlines() if l.startswith("refused %s:" % name))
        assert reason in line, (name, line)
    line = next(l for l in run.stdout.splitlines() if l.startswith("refused bad-zone-truncated:"))
    assert "fog" not in line, line
    # RQ-108: login_closed off the login screen, for that reason.
    line = next(l for l in run.stdout.splitlines() if l.startswith("refused bad-login-closed-off-login:"))
    assert "login_closed off the login" in line, line
    # RQ-109: a bar action off the select, and a select of no info text.
    line = next(l for l in run.stdout.splitlines() if l.startswith("refused bad-select-bar-off-select:"))
    assert "select action off the select" in line, line
    line = next(l for l in run.stdout.splitlines() if l.startswith("refused bad-select-no-info:"))
    assert "front end screen action unbound" in line, line
    # RQ-111: yes or no off the message box, and exit_confirm without both,
    # each for its own reason.
    # RQ-130: create's race and class choices, each refusal for its reason.
    for name, reason in (("bad-version-20", "front end version"),
                         ("bad-version-21", "front end version"),
                         ("bad-version-22", "front end version"),
                         ("bad-version-24", "front end version"),
                         ("bad-node-flags-8", "front end node state"),
                         ("bad-node-flags-64", "front end node state"),
                         ("bad-create-choice-unlisted", "front end create "),
                         ("bad-create-choice-two-chosen", "front end create choice at open"),
                         ("bad-create-choice-disabled", "front end create choice"),
                         ("bad-create-choice-text", "front end create choice"),
                         ("bad-create-choice-off-create", "front end create choice off create"),
                         ("bad-class-label-off-create", "front end class label off create"),
                         ("bad-class-label-both", "front end class label"),
                         ("bad-class-label-unlisted", "front end create class label"),
                         ("bad-class-label-mixed", "front end create class label"),
                         ("bad-choice-race-node", "front end create race button"),
                         ("bad-choice-race-unbound", "front end create race button"),
                         ("bad-choice-race-0", "front end create race button"),
                         ("bad-choice-race-65536", "front end create race button"),
                         ("bad-choice-race-default-0", "front end create race button"),
                         ("bad-choice-race-twice", "front end create race button"),
                         ("bad-choice-race-missing", "front end create race button"),
                         ("bad-choice-class-node", "front end create class button"),
                         ("bad-choice-class-twice", "front end create class button"),
                         ("bad-choice-class-missing", "front end create class button"),
                         ("bad-choice-class-no-specialty", "count"),
                         ("bad-choice-class-17-specialties", "count"),
                         ("bad-choice-class-specialty-shared", "front end create class specialty"),
                         ("bad-choice-class-specialty-0", "front end create class specialty"),
                         ("bad-choice-class-image-text", "front end create class image"),
                         ("bad-choice-class-image-twice", "front end create class image"),
                         ("bad-choice-class-label-unflagged", "front end create class label"),
                         ("bad-choice-class-label-twice", "front end create class label"),
                         ("bad-choice-class-label-unnamed", "front end create class label")):
        line = next(l for l in run.stdout.splitlines() if l.startswith("refused %s:" % name))
        assert reason in line, (name, line)
    assert any(l.startswith("refused bad-choice-truncated:") for l in run.stdout.splitlines())
    for name in ("ok-create-choice", "ok-create-choice-chosen", "ok-create-choice-shown",
                 "ok-create-choice-race-only"):
        assert not any(l.startswith("refused %s:" % name) for l in run.stdout.splitlines()), name
    # RQ-172: the loaded buttons, as the cook wrote them (choice_section).
    at = {i: k for k, (i, _, _) in enumerate(node_records(CHOICE[2]))}
    buttons = next(l for l in run.stdout.splitlines() if l.startswith("create-buttons ok-create-choice:"))
    assert buttons.split(": ", 1)[1] == "races=%d/2/102 classes=%d/101+201/%d/%d;%d/104+204/%d/%d+%d" % (
        at["btn_race_ka_tu"], at["btn_class_warrior"], at["img_warrior"], at["str_01"], at["btn_class_priest"],
        at["img_priest"], at["str_01"], at["int_01"]), buttons
    # RQ-158: each create model's race, its one clip and the demo's joints, in
    # file order; 1 to 32 models, each race 1 to 65535 once.
    race_lines = {l.split(":")[0]: l.split(": ", 1)[1].split() for l in run.stdout.splitlines()
                  if l.startswith("create-races ")}
    assert set(race_lines) == {"create-races ok-create-races", "create-races ok-create-races-32"}, race_lines
    three = race_lines["create-races ok-create-races"]
    assert [x.split("/")[:2] for x in three] == [["2", "1"], ["3", "1"], ["13", "1"]], three
    assert len({x.split("/")[2] for x in three}) == 1 and three[0].split("/")[2] != "0", three
    assert [x.split("/")[0] for x in race_lines["create-races ok-create-races-32"]] == [str(r) for r in range(1, 33)]
    for name, reason in (("bad-version-23", "front end version"), ("bad-create-races-0", "count"),
                         ("bad-create-races-33", "count"), ("bad-create-race-0", "front end create race"),
                         ("bad-create-race-65536", "front end create race"),
                         ("bad-create-race-twice", "front end create race")):
        line = next(l for l in run.stdout.splitlines() if l.startswith("refused %s:" % name))
        assert reason in line, (name, line)
    assert any(l.startswith("refused bad-create-races-truncated:") for l in run.stdout.splitlines())
    for name, reason in (("bad-yes-off-message", "yes/no off the message box"),
                         ("bad-exit-confirm-no-buttons", "exit_confirm without yes and no"),
                         ("bad-exit-confirm-no-no", "exit_confirm without yes and no")):
        line = next(l for l in run.stdout.splitlines() if l.startswith("refused %s:" % name))
        assert reason in line, (name, line)
    # RQ-116: the select's ESC, back unless the package says exit or (RQ-119)
    # none; a value past none refused for that reason.
    escapes = [l for l in run.stdout.splitlines() if l.startswith("escape ")]
    assert escapes == ["escape ok-select-escape-exit: 1", "escape ok-select-escape-none: 2"], escapes
    line = next(l for l in run.stdout.splitlines() if l.startswith("refused bad-select-escape:"))
    assert "front end select escape" in line, line
    # RQ-112: Back lands on the login unless the package says realms; a value
    # past realms refused for that reason.
    backs = [l for l in run.stdout.splitlines() if l.startswith("back ")]
    assert backs == ["back ok-select-back-realms: 1"], backs
    line = next(l for l in run.stdout.splitlines() if l.startswith("refused bad-select-back:"))
    assert "front end select back" in line, line
    # RQ-113: the arrow at the end of the row is hidden unless the package
    # says draw; a value past draw refused for that reason.
    arrow_lines = [l for l in run.stdout.splitlines() if l.startswith("arrows ")]
    assert arrow_lines == ["arrows ok-select-arrows-draw: 1"], arrow_lines
    line = next(l for l in run.stdout.splitlines() if l.startswith("refused bad-select-arrows:"))
    assert "front end select arrows" in line, line
    # RQ-125: create over the hall with each slot's create yaw; a mode past
    # hall, a char_view where the mode does not draw one (or none where it
    # does) and a yaw past a turn, each refused for its reason.
    create_lines = [l for l in run.stdout.splitlines() if l.startswith("create ")]
    assert create_lines == ["create ok-placed-1298: 1 yaws -3.75", "create ok-slide-floor-least: 1 yaws -3.75",
                            "create ok-create-hall: 1 yaws -3.75",
                            "create ok-create-hall-3: 1 yaws -3.71755147 -2.495821 -4.93928194"], create_lines
    for name, reason in (("bad-create-mode", "front end create mode"), ("bad-create-hall-view", "front end create view"),
                         ("bad-create-screen-no-view", "front end create view"),
                         ("bad-create-yaw", "front end create yaw"), ("bad-create-yaw-nan", "finite"),
                         ("bad-version-18", "front end version")):
        line = next(l for l in run.stdout.splitlines() if l.startswith("refused %s:" % name))
        assert reason in line, (name, line)
    # RQ-126: the slide's refusals are the section's own; the 1298 recipe's
    # slide, as the client runs it on the placed layout, moves the panels
    # frame by frame as 1298's Tick does at each size and frame time, ending
    # on the frame 1298 clears its flag, a test hook's rest at the moves.
    for name in SLIDE_CASES:
        if name.startswith("bad-") and name not in ("bad-slide-missing", "bad-slide-truncated", "bad-version-19"):
            line = next(l for l in run.stdout.splitlines() if l.startswith("refused %s:" % name))
            assert "front end slide" in line or "count" in line, (name, line)
    line = next(l for l in run.stdout.splitlines() if l.startswith("refused bad-version-19:"))
    assert "front end version" in line, line
    slide_runs = 0
    for m in re.finditer(r"^slide (\S+): size=(\d+)x(\d+) dt=(\S+) nodes=(\d+) frames=(\S+) rest=(\S+)$",
                         run.stdout, re.M):
        name, width, height, dt = m.group(1), int(m.group(2)), int(m.group(3)), float(m.group(4))
        frames = [tuple(float(v) for v in frame.split(",")) for frame in m.group(6).split(";")]
        rest = tuple(float(v) for v in m.group(7).split(","))
        if name == "ok-slide-floor-least":
            # The least floor still carries the lead past w to its rest.
            assert frames[-1][0] == width - 264 and frames[-1] != frames[-2], m.group(0)[-200:]
            continue
        if name == "ok-slide-screen":
            # The synthetic create's root from the window's right edge to its rest.
            assert m.group(5) == "1" and frames[0][0] == width and frames[-1] == rest, m.group(0)[:200]
            continue
        assert name == "ok-placed-1298" and m.group(5) == "3", m.group(0)[:200]
        dt = min((1 / 30, 1 / 60, 1 / 144, 0.25), key=lambda v: abs(v - dt))
        want = ko_slide(width, height, dt)
        assert frames == [tuple(map(float, frame)) for frame in want], (width, dt, frames[-3:], want[-3:])
        assert rest == (width - 264, height - 734, 50, height - 732, (width - 363) // 2, height - 102), rest
        slide_runs += 1
    assert slide_runs == 12, slide_runs
    print("PASS front-end slide: the 1298 recipe's create slide frame by frame as 1298's Tick (00606450) moves "
          "its panels at 1024x768, 1280x1024 and 1600x1200 and 30, 60, 144 and 4 frames a second; %d refusals"
          % sum(name.startswith("bad-") for name in SLIDE_CASES))
    exit_line = [l for l in run.stdout.splitlines() if l.startswith("message ok-exit-confirm: ")]
    assert exit_line == ["message ok-exit-confirm: %d title='' replaces=1 text='Enter a name. '"
                         % EXIT_INDEX], exit_line
    # RQ-102: the loaded messages, by FrontMessage index; the message refusals
    # are the section's own.
    worded = [l for l in run.stdout.splitlines() if l.startswith("message ok-messages: ")]
    assert worded == ["message ok-messages: 2 title='' replaces=1 text='Realm words.'",
                      "message ok-messages: 5 title='Failed' replaces=1 text='Enter a name. '",
                      "message ok-messages: 6 title='Failed' replaces=0 text=''"], worded
    for name in MESSAGE_CASES:
        if name.startswith("bad-message-") and name != "bad-message-truncated":
            line = next(l for l in run.stdout.splitlines() if l.startswith("refused %s:" % name))
            assert "front end message" in line or "front end text" in line or "count" in line, line
    # RQ-106: the placement's refusals are the section's own; the client puts
    # each node where KO's own code puts it at every size (the window of 800
    # x 600, smaller than the canvas, scales the canvas down instead), and
    # with the scale flag the canvas scaled to fit the window.
    for name in PLACEMENT_CASES:
        if name.startswith("bad-") and name not in ("bad-placement-missing", "bad-placement-truncated"):
            line = next(l for l in run.stdout.splitlines() if l.startswith("refused %s:" % name))
            assert "front end placement" in line or "front end move" in line or "count" in line, line
    placed = {}
    for m in re.finditer(r"^placed (\S+): layout=(\d) size=(\d+)x(\d+) node=(\d+) rect=(\S+)$", run.stdout, re.M):
        placed[(m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5)))] = \
            tuple(float(v) for v in m.group(6).split(","))
    checked = 0
    for width, height in SIZES:
        scale = min(width / 1024, height / 768)
        for layout, n in enumerate(fe.SCREENS):
            for ident, (index, rect) in PLACED_NODES[n].items():
                got = placed[("ok-placed", layout, width, height, index)]
                scaled = placed[("ok-placed-scaled", layout, width, height, index)]
                ox, oy = (width - 1024 * scale) / 2, (height - 768 * scale) / 2
                want = tuple(v * scale + (ox if k % 2 == 0 else oy) for k, v in enumerate(rect))
                assert all(abs(a - b) < 1e-3 for a, b in zip(scaled, want)), (n, ident, width, scaled, want)
                if width < 1024:
                    assert got == scaled, (n, ident, width, got, scaled)
                    continue
                ko = ko_rects(width, height)[n].get(ident)
                if ko is not None:
                    assert got[:2] == ko and got[2] - got[0] == rect[2] - rect[0], (n, ident, width, got, ko)
                    checked += 1
    assert checked == 4 * sum(len(v) for v in ko_rects(1024, 768).values()), checked
    # RQ-109: 1298's select bar where 1298's 00606c10 puts it at each size.
    bar_checked = 0
    for width, height in SIZES:
        if width < 1024:
            continue
        for ident, (index, rect) in BAR_PLACED_NODES["select"].items():
            got = placed[("ok-placed-bar", 1, width, height, index)]
            ko = ko_rects(width, height, bar=True)["select"].get(ident)
            if ko is not None:
                assert got[:2] == ko and got[2] - got[0] == rect[2] - rect[0], (ident, width, got, ko)
                bar_checked += 1
    assert bar_checked == 4 * len(ko_rects(1024, 768, bar=True)["select"]), bar_checked
    # RQ-125: 1298's in-select create where 1298's Load and Tick leave it.
    for width, height in SIZES:
        if width < 1024:
            continue
        for ident, (index, rect) in HALL_PLACED_NODES["create"].items():
            got = placed[("ok-placed-1298", 2, width, height, index)]
            ko = ko_rects(width, height, hall_create=True)["create"].get(ident)
            if ko is not None:
                assert got[:2] == ko and got[2] - got[0] == rect[2] - rect[0], (ident, width, got, ko)
                bar_checked += 1
    print("PASS front-end placement: %d nodes where KO's code puts them at 1024x768, 1280x1024, 1600x1200 and "
          "1281x1025, the canvas scaled at 800x600 and with the scale flag; 1298's select bar's and in-select "
          "create's %d nodes where 1298 puts them" % (checked, bar_checked))
finally:
    shutil.rmtree(work)
