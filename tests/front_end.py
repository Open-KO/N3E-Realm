"""Spec 11 acceptance 1 and 2 (make test): the front-end cook's bounds on
original synthetic UIF fixtures, and the client loader (build/client/
n3e-front-end-check) on a synthetic front-end.bin and its malformed variants.
No reference assets: the UIF trees, the texture and the font atlas are written
here, and both scenes use the demo package's own N3S1 character."""
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/assetc"))
from common import f, string, u  # noqa: E402
import ko_front_end as fe  # noqa: E402

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

# --- the loader ----------------------------------------------------------------

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


def blob(version=2, slots=1, screen_data=None, font_index=None, light=None, plug=None, extra=b"", slot_count=None,
         canvas=(1024, 768), magic=b"N3FE", strings=None):
    tex = [(w, h, rgba) for w, h, rgba in textures.list] + [FONT]
    out = magic + u(version) + u(slots) + u(canvas[0]) + u(canvas[1])
    out += u(len(tex)) + b"".join(u(w) + u(h) + rgba for w, h, rgba in tex)
    out += u(1) + u(len(tex) - 1 if font_index is None else font_index) + u(16) + u(12) + u(4) + f([6] * 95)
    out += b"".join(screen_data or screens)
    out += b"".join(string(s) for s in (strings or ["Level: {level}", "ENTER", "Priest", "Heals.", "Loading",
                                                    "Ver. {version}"]))
    lights = u(1) + raw_light(light or LIGHT)
    plugs = u(0) if plug is None else u(1) + u(plug) + MESH
    character = u(len(model)) + model + u(0) + plugs
    out += CAMERA + lights + f([0, 0, 0]) + character + u(0) + f([100, 50, 400, 350])
    spot = dict(LIGHT, kind=fe.SPOT, theta=0.5, phi=0.6, range=6.0)
    out += CAMERA + u(0) + f([0, 0, 0]) + u(slots if slot_count is None else slot_count)
    out += (f([0, -1, 2, 0, 0, 0, 7]) + fe.light_record(spot)) * (slots if slot_count is None else slot_count)
    out += u(1) + MESH + character + character
    return out + extra


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
    "bad-version": blob(version=1),
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
