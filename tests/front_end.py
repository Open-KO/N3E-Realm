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
import math
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


def blob(version=7, slots=1, screen_data=None, font_index=None, light=None, plug=None, extra=b"", slot_count=None,
         canvas=(1024, 768), magic=b"N3FE", strings=None, music=NO_MUSIC, select_clips=3, blends=None,
         spot_rate=0.6, front_clip=0, turn=0, paths=None, hall=1):
    tex = [(w, h, rgba) for w, h, rgba in textures.list] + [FONT]
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
    out += f([spot_rate]) + (b"" if front_clip is None else u(front_clip))
    if paths is None:
        paths = (u(5) + PATHS3 if slots == 3 else u(1) + path()) if turn == 1 else u(0)
    out += u(turn) + paths + u(hall) + MESH * hall + character(select_clips, plug=plug) + character(plug=plug)
    return out + music + extra


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


# KO's login bar has no status line: a login screen without `notice` cooks
# and loads.
plain = {n: spec(n) for n in fe.SCREENS}
plain["login"]["bindings"].pop("notice")
valid = blob()
cases = {
    "ok-no-notice": blob(screen_data=cook_screens(specs=plain)[0]),
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
    "bad-music-missing": valid[:-len(NO_MUSIC)],
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
    sys.stdout.write(run.stdout)
    assert run.returncode == 0, run.stdout + run.stderr
finally:
    shutil.rmtree(work)
