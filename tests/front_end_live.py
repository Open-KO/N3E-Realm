"""Opt-in (make live-ko): spec 11 acceptance 5 and 6 on the Moradon package cooked
from the player's own KO data.

5. Each front end games/moradon offers (front-ends.json, RQ-078) cooks twice
   with identical bytes and the client loader (build/client/n3e-front-end-check)
   takes it (the 1097 choice's screens from the 1264 install, RQ-085); the one realm-config.json chooses is the bytes the package holds
   (the `moradon` prepare step's cook). The 1298 recipe, not offered yet
   (RQ-086), cooks the same way from the pinned tree with 1298's select
   character and camera paths (RQ-087), no hall and its select zone and fog
   (RQ-095), and the loader takes it.
6. The test client draws each screen at rest at 1024x768, 1280x1024 and
   1600x1200 (KO's sizes, the launcher's windows; N3E_TEST_FRONT_END,
   client/harness/front_end_captures.inc) and this script checks the frames:
   - placement (RQ-106, Q82, KO-FINDINGS 9.3): every layout drawn unscaled on
     the window's own pixels, where 1264's code places it at that size, worked
     out here from the 1264 layouts themselves: the login's root centred on the
     bottom edge and the server group at the window's top-left, the select's
     buttons on its bottom edge (1264's CUICharacterSelect::Load), create,
     loading and the message box centred (the version text at 10, 10), the
     logo centred;
   - login: the intro character is drawn and its projected box covers the view's
     centre (KO's close-up runs past the frame's edges), and the login button's
     rect holds its art (not one flat colour);
   - realms: the list shows the realm's name: against the same frame with an
     unnamed realm, pixels differ inside the list's rect and nowhere else;
   - the login's copyright line (RQ-108, Q85, KO-FINDINGS 9.4: 1264's
     SetVisibleLogInUIs): the login group draws at rest, the line (bound to
     login_closed) instead while a login is under way and on the realm list
     (the client's own report of each state); with a login under way the line
     is where 1264 puts it, ((W - w) / 2, H - h - 20), its white glyphs drawn
     there, and the frame differs from the login at rest only within the bar
     and the line, and from the realm list only within the server group;
   - select: 1, 2 and 3 characters drawn, each box non-empty and inside the view;
   - the select arrows at the ends of the row (RQ-113, KO-FINDINGS 9.13): the
     chosen package and the 1298 recipe draw both (select.arrows draw), as no
     KO select hides one (RQ-124: the 1097 choice as 1264's);
   - create: the create model stands (KO's InitChr model breathing, not the hall's
     seated clip): its box is clearly taller than wide; and the stone background
     shows no seams (KO's UI point sampling on whole pixels): no column of a band
     across its top is darker than 0.6 of the band's mean; the recipe's buttons
     fixed `down` (RQ-138, Q89 (b), KO-FINDINGS 9.16: the 1097 choice's Tuarek
     and priest) draw their down image's texels, as 1264 draws its chosen race
     and class (0043ec90, 0043ee10, 00403a70), over 85% of their rect (the
     rest under the label) and their on image's under half; the stat labels
     the recipe draws (RQ-144, Q92 (b), KO-FINDINGS 9.16: the 1097 choice's
     img_str and img_int, 1264's after a priest click, 0043ee10) turn their
     text pink, the hidden ones leaving it light;
   - loading: the progress bar's lit share grows from the start stage (2/3: the
     package and its textures) to the first World (1);
   - message: the box's text rect holds text (RQ-085: 1264's El_MessageBox_us,
     its OK button only, as KO's MessageBoxPost shows an MB_OK box); the same
     text as a refused create, which the package titles (RQ-102, Q81: 1264's
     create failure title), differs from it inside the title's rect (and
     the few pixels its glyphs stand past it) and nowhere else, so an
     untitled message draws no title;
   - logo (RQ-101, KO-FINDINGS 9.2: 1264's logo procedure, first in the
     process): each of co_usa_logo_us.uif's three groups in its hold draws its
     art (K2 Network, presents, Knight Online) in the layout's rect and black
     everywhere else; half way into the first group's fade-in its art is drawn
     at 127/255 of its brightness; the screen is 12 s long (1.5, 1 and 1.5 s
     fades to KO's peak 1.5), skips on a key, hides the cursor and gives way to
     the login once it has run;
   - music (RQ-018, Q57; RQ-083, KO-FINDINGS 9): login and the realm list
     name one track, select and create another, loading none: 1097's
     Snd/bgm_login.wav (PCM, 477,749 frames at 22,050 Hz stereo), which
     restarts at its first sample every 21.66 s, and Snd/bgm_el_battle.wav
     (PCM, 3,995,263 frames), which loops; each streams audibly one second
     past its end without ending. The logo (RQ-101): 1264's Snd/bless.wav
     (PCM, 305,280 frames at 22,050 Hz mono), once, from 1 s in, faded out
     over 4 s from the third group.
   - the 1298 recipe's select (RQ-109, KO-FINDINGS 9.6): its cook swapped into
     the chosen package (the release index rewritten) draws 1298's
     co_CharacterSelect_us.uif bar unscaled at ((W - w) >> 1, H - 10 - h)
     (00606c10), its ten bound nodes where that puts them, its art drawn, and
     its name, level and class texts filled for a character and empty with none;
   - the 1298 recipe's exit (RQ-111, KO-FINDINGS 9.7): a click on the bar's
     Exit asks in El_MessageBox_us.uif with its Yes and No and without its OK
     (SetBoxStyle 00527a40), centred (005282a0); ESC and No close it, ENTER,
     the keypad's ENTER and Yes leave the game, the hidden OK does nothing
     (OnKeyPress 00527c60, ReceiveMessage 00526d00); the frame draws Yes and
     No where the OK box draws OK, row 1502's text in the message rect;
   - the chosen package's exit (RQ-115, KO-FINDINGS 9.8): 1264's bt_exit
     (00444e60) asks the same in 1264's El_MessageBox_us.uif (0050c730,
     SetBoxStyle 0050bfb0, OnKeyPress 0050c1d0, ReceiveMessage 0050b510), so
     the chosen package's select checks as the 1298 recipe's;
   - the select's ESC (RQ-116, KO-FINDINGS 9.8): the chosen package's asks
     the exit question, as 1264's select OnKeyPress (004454e0) presses
     bt_exit for DIK_ESCAPE; the 1298 recipe's does nothing (RQ-119,
     KO-FINDINGS 9.9: 1298's bar OnKeyPress 00607810 presses no button);
     while a start clip plays (RQ-121, KO-FINDINGS 9.10), ESC and a click on
     Exit do nothing in either, as KO's select takes no input then;
   - the select's Back (RQ-112, KO-FINDINGS 9.12): a click on it at rest is
     the Back command in either, and both land on the realm list, as 1298's
     Back sets its login procedure's +0x21 (00607160, Init 005f68e0) and
     1264's +0x35 (00445145, Init 005bd9b0; RQ-123, the maintainer's choice);
     after it the chosen package's login and realm list draw no copyright
     line, as 1264's Init hides Group_LogIn alone;
   - the 1298 recipe's create (RQ-114, RQ-125, KO-FINDINGS 9.14, 9.15): Create
     from an occupied slot opens 1298's in-select create
     (co_characterCreate_us.uif) at once over the hall, the camera flying to
     the first empty slot behind it on ka_left_right, which neither key
     skips, the new character standing there once the camera is and
     (RQ-130) the race is clicked; ESC there,
     or one frame into the flight, returns to the select at rest on that
     slot with the bar shown; at rest its name entry is where Group_name's
     slide clamps ((W - w) / 2, H - 30 - h), no new character before a race
     click (RQ-130), the hall's terrain between the panels;
   - the 1298 recipe's create slide (RQ-126, KO-FINDINGS 9.15): ENTER on an
     empty slot opens create with its three panels sliding in from the right,
     the left and the bottom edge, frame by frame (1/32 s apart) where 1298's
     Tick (00606450) puts them on the pinned layout's rects, ending on the
     frame it clears its flag; the chosen package has no slide;
   - the 1298 recipe's race and class (RQ-130, KO-FINDINGS 9.15, Q87 (b)):
     create opens with neither chosen and no new character; Create says row
     1908 (no race) or 1904 (no class) under row 1901, as 1298's 005fffd0
     and 00600750 do, a race click unchoosing the class (00604f90); the new
     character stands once the race is clicked, at the slot the camera was
     on for that click (005fd120), and a chosen button draws down; with both
     clicked Create sends. The chosen package's create waits for neither;
   - the 1298 recipe's class buttons and images (RQ-133, KO-FINDINGS 9.15):
     each open draws every class button over its img_* (the reset 006066b0's
     00605950 shows them all); the race click hides the warrior and mage
     buttons, their images standing in their place, and the rogue and priest
     images (006060f0(2)); a Cancel and a new open draw them all again.

No server or stack.
"""
import json
import math
import os
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "tools/assetc"))
WORK = Path(os.environ.get("N3E_KO_WORK", "build/live-ko/work"))
B = ROOT / "build/live-ko/front-end"
B.mkdir(parents=True, exist_ok=True)
package = WORK / "packages" / "moradon"

if os.environ.get("N3E_GRAPHICAL") != "1":
    print("UNVERIFIED KO front end needs N3E_GRAPHICAL=1 (make live-ko)")
    sys.exit(0)

# --- 5: the cook ---------------------------------------------------------------
import ko_front_end  # noqa: E402

import front_end_choice  # noqa: E402

# RQ-078: every front end games/moradon offers (front-ends.json) cooks twice to
# the same bytes and the client loader takes it; the one realm-config.json
# chooses is the package's own.
chosen = front_end_choice.choose("games/moradon")["client"]
for client in sorted(front_end_choice.catalogue("games/moradon")):
    front = front_end_choice.resolve("games/moradon", client)
    cooked = []
    for i in range(2):
        out = Path(tempfile.mkdtemp(prefix="front-end-%s-" % client, dir=B))
        report = ko_front_end.cook(ko_front_end.inputs(front), out, front["recipe"], out / "work")
        cooked.append((out / "front-end.bin").read_bytes())
    assert cooked[0] == cooked[1], "the %s front-end cook is not deterministic" % client
    if client == chosen:
        # RQ-102: whether the chosen recipe titles a refused create (the
        # message-titled capture below checks the title only then).
        titled_create = bool((report["messages"].get("create_refused") or {}).get("title"))
    if client == "1097":
        # RQ-085 (KO-FINDINGS 9.2): the 1097 choice draws the 1264 client's
        # screens: every layout and the textures they name come from the 1264
        # install (each checked against its installer's manifest), 1264's
        # message box and its loading screen with no war victor among them.
        layouts = sorted(s for s in report["sources"] if "/" in s and s.split(":")[-1].lower().startswith("ui_us/"))
        assert layouts and all(s.startswith("installer-1264:") for s in layouts), layouts
        names = {s.split(":", 1)[1].lower() for s in layouts}
        assert {"ui_us/el_messagebox_us.uif", "ui_us/ui_message_us.dxt", "ui_us/co_loading_us.uif"} <= names, names
    # The checker exits 1 unless it also saw a refusal (tests/front_end.py
    # passes both kinds); one `ok` package loaded is its own PASS line.
    loaded = subprocess.run(["build/client/n3e-front-end-check", "ok", str(out)], capture_output=True, text=True)
    assert "PASS front-end loader: 1 loaded, 0 refused" in loaded.stdout, \
        "the client loader refuses the %s front end: %s%s" % (client, loaded.stdout, loaded.stderr)
    if client == chosen:
        assert cooked[0] == (package / "front-end.bin").read_bytes(), "the package's front-end.bin is not this cook's"
    print(f"PASS front-end cook {client}: twice identical, {len(cooked[0])} bytes, the client loads it"
          + (", the package's own (realm-config.json)" if client == chosen else "")
          + (", its screens the 1264 install's (RQ-085)" if client == "1097" else ""))

# RQ-086: games/moradon/front-end-1298.json, not offered yet (content/front-end.md,
# "1298"), still cooks from the pinned tree to the same bytes twice, in the loop
# front-clip mode with 1298's per-race select character, and the client loads it.
# RQ-087: in the path turn mode, with the recipe's .n3camera paths and no hall.
# RQ-095: with the recipe's select zone (its terrain and shapes) and fog.
recipe_1298 = json.loads(Path("games/moradon/front-end-1298.json").read_text())
camera_paths = {p["path"] for p in recipe_1298["select"]["paths"]}
assert recipe_1298["select"]["turn"] == "path" and "hall" not in recipe_1298["select"], recipe_1298["select"]
assert "zone" in recipe_1298["select"] and recipe_1298["select"].get("fog") is True, recipe_1298["select"]
pinned = ko_front_end.inputs(front_end_choice.resolve("games/moradon", "1097"))
cooked = []
for i in range(2):
    out = Path(tempfile.mkdtemp(prefix="front-end-1298-recipe-", dir=B))
    report = ko_front_end.cook(pinned, out, Path("games/moradon/front-end-1298.json"), out / "work")
    cooked.append((out / "front-end.bin").read_bytes())
# RQ-130 (KO-FINDINGS 9.15): the recipe words create's two refusals with
# 1298's rows (00600750: code 7 row 1908, code 9 row 1904, each under 1901),
# as the cook read them from the pinned tree's table.
assert recipe_1298["messages"]["create_no_race"] == {"title": {"table": "Data/Texts_us.tbl", "row": 1901},
                                                     "text": {"table": "Data/Texts_us.tbl", "row": 1908}}
assert recipe_1298["messages"]["create_no_class"] == {"title": {"table": "Data/Texts_us.tbl", "row": 1901},
                                                      "text": {"table": "Data/Texts_us.tbl", "row": 1904}}
choice_boxes = [f"{k}|{report['messages'][k]['title']}|{report['messages'][k]['text']}"
                for k in ("create_no_race", "create_no_class")]
assert cooked[0] == cooked[1], "the 1298 recipe's cook is not deterministic"
front_end_1298 = out / "front-end.bin"
assert cooked[0][4:8] == ko_front_end.VERSION.to_bytes(4, "little"), cooked[0][:8]
sources = set(report["sources"])
assert {"ChrSelect/upc_ka_tu.n3joint", "ChrSelect/upc_ka_tu.n3anim"} <= sources, sorted(sources)
assert not any("upc_ka_tu_pri" in s or "wea_ka_mace" in s for s in sources), sorted(sources)
assert camera_paths <= sources, sorted(camera_paths - sources)
assert not any(s.lower().endswith(".n3shape") for s in sources), sorted(sources)
zone = report["zone"]
assert zone["key"] == recipe_1298["select"]["zone"], zone
assert {zone[k].replace("\\", "/") for k in ("terrain", "colour_map", "objects")} <= sources, (zone, sorted(sources))
assert 0 < zone["blended_meshes"] < zone["meshes"] <= ko_front_end.MAX_ZONE_MESHES, zone
assert any(s.startswith("Object/") and s.lower().endswith(".n3pmesh") for s in sources), sorted(sources)
assert len(cooked[0]) <= 64 << 20, len(cooked[0])
loaded = subprocess.run(["build/client/n3e-front-end-check", "ok", str(out)], capture_output=True, text=True)
assert "PASS front-end loader: 1 loaded, 0 refused" in loaded.stdout, \
    "the client loader refuses the 1298 recipe's front end: %s%s" % (loaded.stdout, loaded.stderr)
# RQ-126 (KO-FINDINGS 9.15): 1298's create slide on the pinned layout's rects,
# as its Tick (00606450) reads, from SetVisible's d = 0 (00606650) to the frame
# it clears its flag: each frame's (Group_race, Group_class, Group_name)
# top-lefts, after the frame's step. d is a float (+0xb8).
def ko_create_slide(tree, width, height, dt):
    def f32(x):
        return struct.unpack("<f", struct.pack("<f", x))[0]

    def size(ident):
        r = find(tree, ident)["rect"]
        return r[2] - r[0], r[3] - r[1]
    (rw, rh), (cw, ch), (nw, nh) = size("Group_race"), size("Group_class"), size("Group_name")
    d, frames = 0.0, []
    while True:
        d = f32(d + max(dt * 1300 * (rw - d) / rw, 2.0))
        race = max(width - math.trunc(d), width - rw - 50)
        frames.append((race, height - 30 - rh, min(math.trunc(d) - cw, 50), height - 30 - ch,
                       int((width - nw) / 2), max(height - math.trunc((nh + 30) * d / (cw + 50)), height - 30 - nh)))
        if race == width - rw - 50:
            return frames


print(f"PASS front-end cook 1298 recipe (not offered): twice identical, {len(cooked[0])} bytes, upc_ka_tu with "
      f"no plug, {len(camera_paths)} camera paths, no hall and the zone {zone['name']} ({zone['meshes']} meshes, "
      f"{zone['blended_meshes']} blended) under its fog, the client loads it")

# --- 6: the captures -----------------------------------------------------------


def pixels(path):
    data = path.read_bytes()
    magic, size, _, body = data.split(b"\n", 3)
    width, height = map(int, size.split())
    assert magic == b"P6" and len(body) == width * height * 3, path
    return width, height, body


def region(path, rect):
    width, height, body = pixels(path)
    x0, y0, x1, y1 = (max(0, v) for v in rect)
    x1, y1 = min(x1, width), min(y1, height)
    return [body[(y * width + x) * 3:(y * width + x) * 3 + 3] for y in range(y0, y1) for x in range(x0, x1)]


def seam_columns(path, width, origin):
    """Columns of the create screen's top stone band (canvas y 10-30, x 20-1000)
    darker than 0.6 of the band's mean: the black texels that border each of
    KO's tiles, blended in. `origin`: where the canvas's (0, 0) is, and the
    scale."""
    _, _, body = pixels(path)
    ox, oy, s = origin
    y0, y1 = int(oy + 10 * s), int(oy + 30 * s)
    cols = [sum(sum(body[(y * width + x) * 3:(y * width + x) * 3 + 3]) for y in range(y0, y1)) / (y1 - y0)
            for x in range(int(ox + 20 * s), int(ox + 1000 * s))]
    mean = sum(cols) / len(cols)
    return sum(c < 0.6 * mean for c in cols)


def lit_share(path, rect):
    """The share of the rect's middle row that is lit (the bar's fill)."""
    width, _, body = pixels(path)
    y = (rect[1] + rect[3]) // 2
    row = [body[(y * width + x) * 3:(y * width + x) * 3 + 3] for x in range(rect[0], rect[2])]
    return sum(sum(p) > 200 for p in row) / len(row)


# RQ-101: the logo layout's groups, as the 1097 choice reads it.
import ko_hud  # noqa: E402

logo_recipe = json.loads(front_end_choice.choose("games/moradon")["recipe"].read_text())["logo"]
logo_tree = ko_hud.parse(ko_front_end.inputs(front_end_choice.resolve("games/moradon", chosen)).get(logo_recipe["ui"]))
LOGO_GROUPS = [next(c for c in logo_tree["children"] if c["id"] == g["node"]) for g in logo_recipe["groups"]]

# RQ-106 (Q82, KO-FINDINGS 9.3): where 1264 puts the layouts' nodes at a
# viewport, from the layouts as the choice reads them and 1264's code.
screen_recipes = json.loads(front_end_choice.choose("games/moradon")["recipe"].read_text())["screens"]
choice_inputs = ko_front_end.inputs(front_end_choice.resolve("games/moradon", chosen))
LAYOUTS = {n: ko_hud.parse(choice_inputs.get(screen_recipes[n]["ui"])) for n in ko_front_end.SCREENS}


def find(tree, ident):
    if tree["id"] == ident:
        return tree
    return next((hit for c in tree["children"] if (hit := find(c, ident))), None)


# RQ-138 (Q89 (b), KO-FINDINGS 9.16): the chosen recipe's create buttons fixed
# `down` (the 1097 choice's Tuarek and priest) draw their down image (state
# image 1), as 1264 draws its chosen race and class (0043ec90 and 0043ee10 set
# state 3, which Render 00403a70 draws with BS_DOWN), not their on image (2):
# each (id, the image's rect on the canvas, its down and on tiles' texels).
def state_tiles(tree, ident):
    images = {c["reserved"]: c for c in find(tree, ident)["children"] if c["kind"] == 4}

    def tile(image):
        w, h, rgba = ko_front_end.texture(create_tree_of_choice.get(image["texture"]))
        x0, y0, x1, y1 = images[1]["rect"]
        u0, v0 = round(image["uv"][0] * w), round(image["uv"][1] * h)
        return [rgba[((v0 + y) * w + u0 + x) * 4:((v0 + y) * w + u0 + x) * 4 + 3]
                for y in range(y1 - y0) for x in range(x1 - x0)]
    assert images[1]["rect"] == images[2]["rect"], (ident, images[1]["rect"], images[2]["rect"])
    return images[1]["rect"], tile(images[1]), tile(images[2])


create_tree_of_choice, _ = choice_inputs.split(screen_recipes["create"]["ui"])
DOWN = {ident: state_tiles(LAYOUTS["create"], ident)
        for ident, state in screen_recipes["create"].get("states", {}).items() if state == "down"}
if chosen == "1097":
    assert sorted(DOWN) == ["btn_class_priest", "btn_race_ka_tu"], sorted(DOWN)


# RQ-139 (KO-FINDINGS 9.16, the maintainer's "Grey button, as 1264"): a create
# button the chosen recipe leaves unfixed and unbound draws its normal image
# (state image 0), as 1264's race buttons at rest (0043ec90 sets them 2, which
# Render 00403a70 draws with BS_NORMAL): the 1097 choice's Puri Tuarek, whose
# disabled image has no texture. Each (id, the image's rect, its texels).
def normal_tile(tree, ident):
    image = next(c for c in find(tree, ident)["children"] if c["kind"] == 4 and c["reserved"] == 0)
    w, h, rgba = ko_front_end.texture(create_tree_of_choice.get(image["texture"]))
    x0, y0, x1, y1 = image["rect"]
    u0, v0 = round(image["uv"][0] * w), round(image["uv"][1] * h)
    return image["rect"], [rgba[((v0 + y) * w + u0 + x) * 4:((v0 + y) * w + u0 + x) * 4 + 3]
                           for y in range(y1 - y0) for x in range(x1 - x0)]


def descendants(tree):
    for c in tree["children"]:
        yield c
        yield from descendants(c)


create_recipe = screen_recipes["create"]
NORMAL = {ident: normal_tile(LAYOUTS["create"], ident) for ident in
          (n["id"] for n in descendants(LAYOUTS["create"]) if n["kind"] == 1 and n["id"].startswith("btn_race_"))
          if ident not in create_recipe.get("states", {}) and ident not in create_recipe.get("bindings", {})
          and ident not in create_recipe.get("hidden", [])}
if chosen == "1097":
    assert sorted(NORMAL) == ["btn_race_ka_pt"], sorted(NORMAL)


# RQ-142 (Q91 (b), KO-FINDINGS 9.16, the maintainer's "Match 1264, Rogue
# inert"): a class image the chosen recipe draws with its button hidden stands
# in the button's place, as 1264's img_warrior and img_mage after a Tuarek
# click (0043ec90(2) hides those buttons and shows their images). Each (id,
# the image's rect, its texels).
def image_tile(tree, ident):
    image = find(tree, ident)
    w, h, rgba = ko_front_end.texture(create_tree_of_choice.get(image["texture"]))
    x0, y0, x1, y1 = image["rect"]
    u0, v0 = round(image["uv"][0] * w), round(image["uv"][1] * h)
    return image["rect"], [rgba[((v0 + y) * w + u0 + x) * 4:((v0 + y) * w + u0 + x) * 4 + 3]
                           for y in range(y1 - y0) for x in range(x1 - x0)]


CLASS_IMAGES = {f"img_{c}": image_tile(LAYOUTS["create"], f"img_{c}") for c in ("warrior", "rogue", "mage", "priest")
                if f"img_{c}" not in create_recipe.get("hidden", [])
                and f"btn_class_{c}" in create_recipe.get("hidden", [])}
if chosen == "1097":
    assert sorted(CLASS_IMAGES) == ["img_mage", "img_warrior"], sorted(CLASS_IMAGES)
    assert {"img_rogue", "img_priest"} <= set(create_recipe["hidden"]), create_recipe["hidden"]


# RQ-144 (Q92 (b), KO-FINDINGS 9.16, the maintainer's "Pink Str/Int, as
# 1264"): each stat label img_* is a pink (0xff8080) root string over a light
# (0xe6e6e6) one with the same text and rect; a priest click shows img_str and
# img_int (0043ee10(104)). A label the chosen recipe draws turns its text pink;
# a hidden one leaves the light text over the grey panel, which holds no pink.
# Each id -> its rect.
STAT_LABELS = {ident: find(LAYOUTS["create"], ident)["rect"]
               for ident in ("img_str", "img_sta", "img_dex", "img_int", "img_map")}
for ident in STAT_LABELS:
    assert find(LAYOUTS["create"], ident)["color"] & 0xffffff == 0xff8080, ident
SHOWN_STATS = [ident for ident in STAT_LABELS if ident not in create_recipe.get("hidden", [])]
if chosen == "1097":
    assert SHOWN_STATS == ["img_str", "img_int"], SHOWN_STATS


def pink_and_light(pixels):
    """(text pixels nearer the pink label's colour, ones of the light label's)."""
    return (sum(p[0] >= 200 and p[0] - max(p[1], p[2]) >= 60 for p in pixels),
            sum(min(p) >= 200 for p in pixels))


def extent(tree):
    """The rect around a node's descendants (not its own rect: a group's
    region is KO's hit area, not what it draws)."""
    rects = []

    def walk(n):
        for c in n["children"]:
            rects.append(c["rect"])
            walk(c)
    walk(tree)
    return [min(r[0] for r in rects), min(r[1] for r in rects), max(r[2] for r in rects), max(r[3] for r in rects)]


def differing(a_path, b_path, inside):
    """Pixels that differ between two frames, (inside any of the rects,
    outside them all)."""
    width, _, a = pixels(a_path)
    _, _, b = pixels(b_path)
    counts = [0, 0]
    for i in range(0, len(a), 3):
        if a[i:i + 3] != b[i:i + 3]:
            x, y = (i // 3) % width, (i // 3) // width
            counts[0 if any(r[0] <= x < r[2] and r[1] <= y < r[3] for r in inside) else 1] += 1
    return tuple(counts)


# RQ-111 (1298) and RQ-115 (1264), KO-FINDINGS 9.7 and 9.8: the select's Exit
# asks row 1502 with Yes and No (MB_YESNO, BEHAVIOR_EXIT) in the box the
# manager loads and centres; ESC and No close it, ENTER, the keypad's ENTER and
# Yes leave, the hidden OK does nothing.
EXIT_ASKS = ("asks=1 shown=0,1,1 plain=1,0,0 esc=closed:none enter=closed:exit "
             "keypad=closed:exit no=closed:none yes=closed:exit ok=open:none")
# RQ-121 (KO-FINDINGS 9.10): ESC and a click on Exit do nothing while the start
# clip plays: 1264's and 1097's select take no input from the select request
# until the main procedure (CharacterSelect 00443570, 0043ea30), nor 1298's
# (005fe7c0).
START_IGNORES = " started=1 start_esc=none start_exit=none"


def check_exit(size, stdout, box_tree, width, height, plain, question, yes, escape, back):
    """The select's exit question against its box, `box_tree` centred at
    ((W - w) >> 1, (H - h) >> 1): the client's report, ESC on the select at
    rest doing `escape` (RQ-116: `asks`; RQ-119: `none`), Back landing on
    `back` (RQ-112: `login` or `realms`), the Yes rect the shot
    names (`yes`), Yes and No drawn where the OK box (`plain`) draws OK and
    the text in the message rect. Returns the box's origin."""
    exits = re.search(r"^FRONT_EXIT (.*)$", stdout, re.M)
    want = EXIT_ASKS + " select_esc=" + escape + START_IGNORES + " back=back:" + back
    assert exits and exits.group(1) == want, (size, exits and exits.group(1), want)
    root = box_tree["rect"]
    bx, by = (width - (root[2] - root[0])) >> 1, (height - (root[3] - root[1])) >> 1
    box_rect = {k: (bx + r[0] - root[0], by + r[1] - root[1], bx + r[2] - root[0], by + r[3] - root[1])
                for k, r in ((k, find(box_tree, k)["rect"]) for k in ("btn_yes", "btn_no", "btn_ok", "Text_Message"))}
    assert tuple(yes) == box_rect["btn_yes"], (size, yes, box_rect["btn_yes"])
    for button in ("btn_yes", "btn_no", "btn_ok"):
        r = box_rect[button]
        inside, _ = differing(plain, question, [(r[0] + 2, r[1] + 2, r[2] - 2, r[3] - 2)])
        assert inside > 200, (size, button, inside)
    for button in ("btn_yes", "btn_no"):
        assert len(set(region(question, box_rect[button]))) > 10, (size, button)
    assert len(set(region(question, box_rect["Text_Message"]))) > 2, (size, "no exit text")
    return bx, by


def ko_placed(width, height):
    """{name: (x0, y0, x1, y1)} of the nodes the captures print, as 1264
    places them on a width x height viewport: the login's root at ((W - w) >>
    1, H - h) (005bde22) and its server group at (0, 0) (005c25b0); the select
    as CUICharacterSelect::Load (004448f0, r = W / 1024 as a float); create
    (0043cd00) and loading (00401670) centred, C's signed division; the message
    box at ((W - w) >> 1, (H - h) >> 1) (0050c730)."""
    def at(node, x, y):
        x0, y0, x1, y1 = node["rect"]
        return (x, y, x + x1 - x0, y + y1 - y0)

    def under(root, ident, x, y):
        node = find(root, ident)
        return at(node, x + node["rect"][0] - root["rect"][0], y + node["rect"][1] - root["rect"][1])

    out = {}
    login = LAYOUTS["login"]
    w, h = login["rect"][2] - login["rect"][0], login["rect"][3] - login["rect"][1]
    out["login"] = under(login, "Btn_Login", (width - w) >> 1, height - h)
    out["realm_list"] = under(find(login, "Group_ServerList"), "List_Server", 0, 0)
    rights = find(login, "Text_Rights")
    rw, rh = rights["rect"][2] - rights["rect"][0], rights["rect"][3] - rights["rect"][1]
    out["login_closed"] = at(rights, int((width - rw) / 2), height - rh - 20)
    select = LAYOUTS["select"]
    r = struct.unpack("<f", struct.pack("<f", width / (select["rect"][2] - select["rect"][0])))[0]
    size = lambda n: (find(select, n)["rect"][2] - find(select, n)["rect"][0],
                      find(select, n)["rect"][3] - find(select, n)["rect"][1])
    (lw, lh), (rw, rh), (ew, eh), (bw, bh) = (size(n) for n in ("bt_left", "bt_right", "bt_exit", "bt_back"))
    out["select_prev"] = at(find(select, "bt_left"), int((width >> 1) - lw - 100 - 26 * r), height - 10 - lh)
    out["select_next"] = at(find(select, "bt_right"), int((width >> 1) + 26 * r + 100), height - 10 - rh)
    out["exit"] = at(find(select, "bt_exit"), (width - ew) >> 1, height - 10 - eh)
    out["back"] = at(find(select, "bt_back"), (width - bw) >> 1, height - 20 - eh - bh)
    for name, ident in (("create", "edit_name"), ("loading", "Progress_Loading"), ("message", "Text_Message")):
        root = LAYOUTS[name]
        w, h = root["rect"][2] - root["rect"][0], root["rect"][3] - root["rect"][1]
        if name == "message":
            x, y = (width - w) >> 1, (height - h) >> 1
        else:
            x, y = int((width - w) / 2), int((height - h) / 2)
        out[name] = under(root, ident, x, y)
    return out


realm = B / "realm.json"
realm.write_text('{"id": "front-end", "name": "Local Realm", "host": "127.0.0.1", "port": 1, '
                 '"discord_client_id": "0"}')
for size in ("1024x768", "1280x1024", "1600x1200"):
    width, height = map(int, size.split("x"))
    run = subprocess.run(["build/client/n3e-test-client", str(package), "--realm", str(realm),
                          "--fixed-window", size],
                         capture_output=True, text=True, timeout=600,
                         env={**os.environ, "N3E_TEST_FRONT_END": str(B / size)})
    (B / f"client-{size}.log").write_text(run.stdout + run.stderr)
    assert run.returncode == 0 and "FRONT_SHOTS done" in run.stdout, (size, run.stdout[-2000:], run.stderr[-2000:])
    # RQ-126: the chosen package's create (1264's, a screen of its own) has no slide.
    assert "FRONT_CREATE_SLIDE" not in run.stdout, size
    # RQ-130: and its race and class stand chosen from the open (Q52).
    assert "FRONT_CREATE_CHOICE" not in run.stdout, size
    shots = {}
    origins = {}
    for m in re.finditer(r"^FRONT_SHOT name=(\S+) size=(\d+)x(\d+) path=(\S+) rect=(\S*) drawn=(\S*) "
                         r"origin=(\S+)$", run.stdout, re.M):
        name, w, h, path, rect, drawn, origin = m.groups()
        assert (int(w), int(h)) == (width, height), (size, m.group(0))
        boxes = [(kind, tuple(map(int, box.split(",")))) for kind, box in
                 (d.split(":") for d in drawn.split(";") if d)]
        shots[name] = (Path(path), tuple(map(int, rect.split(","))) if rect else None, boxes)
        origins[name] = tuple(map(float, origin.split(",")))
    # RQ-106: every screen unscaled, each node where 1264 puts it at this size.
    assert {o[2] for o in origins.values()} == {1.0}, (size, origins)
    want = ko_placed(width, height)
    placed = dict(re.findall(r"(\w+)=(\S+)", re.search(r"^FRONT_PLACED (.*)$", run.stdout, re.M).group(1)))
    got = {k: tuple(map(int, v.split(","))) for k, v in placed.items()}
    for name, shot_name in (("login", "login"), ("realm_list", "realms"), ("login_closed", "login-waiting"),
                            ("create", "create"), ("loading", "loading-start"), ("message", "message")):
        got[name] = shots[shot_name][1]
    assert got == want, (size, {k: (got.get(k), v) for k, v in want.items() if got.get(k) != v})
    assert set(shots) == {"login", "login-waiting", "realms", "realms-unnamed", "select-1", "select-2", "select-3", "create",
                          "loading-start", "loading-world", "message", "message-titled", "message-exit", "logo-0",
                          "logo-1", "logo-2", "logo-fade"}, shots.keys()

    path, rect, boxes = shots["login"]
    assert [k for k, _ in boxes] == ["intro"], boxes
    x0, y0, x1, y1 = boxes[0][1]
    assert x0 < width / 2 < x1 and y0 < height / 2 < y1, (size, boxes)
    art = region(path, rect)
    assert len(set(art)) > 50 and rect[2] - rect[0] > 40, (size, rect, len(set(art)))

    named, rect, _ = shots["realms"]
    unnamed = shots["realms-unnamed"][0]
    _, _, a = pixels(named)
    _, _, b = pixels(unnamed)
    inside = outside = 0
    for i in range(0, len(a), 3):
        if a[i:i + 3] != b[i:i + 3]:
            x, y = (i // 3) % width, (i // 3) // width
            if rect[0] <= x < rect[2] and rect[1] <= y < rect[3]:
                inside += 1
            else:
                outside += 1
    assert inside > 50 and outside == 0, (size, rect, inside, outside)
    realm_name = inside

    # RQ-108: the copyright line instead of the bar while a login is under way
    # and on the realm list, where 1264 puts it; RQ-123: neither the bar nor
    # the line through a Back's login and on the list after it (1264's Init
    # 005bd9b0 hides Group_LogIn alone, never calling SetVisibleLogInUIs).
    states = re.search(r"^FRONT_LOGIN (.*)$", run.stdout, re.M)
    assert states and states.group(1) == "idle=1,0,0 waiting=0,0,1 realms=0,1,1 back=0,0,0 back_realms=0,1,0", \
        (size, states and states.group(1))
    # RQ-124 (the maintainer, 2026-11-03: "Draw both, as 1264"): the chosen
    # package draws both arrows at each end of the row (select.arrows draw), as
    # 1264's select never hides one (004448f0, 00444e60, 004454e0; KO-FINDINGS
    # 9.13).
    arrows = re.search(r"^FRONT_ARROWS (.*)$", run.stdout, re.M)
    assert arrows and arrows.group(1) == "left=1,1 right=1,1", (size, arrows and arrows.group(1))
    # RQ-115 (KO-FINDINGS 9.8): the chosen package's select Exit asks as
    # 1264's bt_exit does (00444e60), in 1264's El_MessageBox_us.uif; RQ-116:
    # its ESC asks the same, as 1264's OnKeyPress (004454e0) presses bt_exit;
    # RQ-123: its Back lands on the realm list, as 1264's (00445145).
    exit_box = check_exit(size, run.stdout, LAYOUTS["message"], width, height, shots["message"][0],
                          shots["message-exit"][0], shots["message-exit"][1], "asks", "realms")
    waiting, line, _ = shots["login-waiting"]
    login = LAYOUTS["login"]
    root_x, root_y = (width - (login["rect"][2] - login["rect"][0])) >> 1, height - (login["rect"][3] - login["rect"][1])
    bx0, by0, bx1, by1 = extent(find(login, "Group_LogIn"))
    bar = (root_x + bx0 - login["rect"][0], root_y + by0 - login["rect"][1],
           root_x + bx1 - login["rect"][0], root_y + by1 - login["rect"][1])
    # KO's strings are not clipped to their rect: a glyph may stand a few
    # pixels past it (as the message title's).
    margin = 8
    glyphs = (line[0] - margin, line[1] - margin, line[2] + margin, line[3] + margin)
    inside, outside = differing(shots["login"][0], waiting, [bar, glyphs])
    assert inside > 1000 and outside == 0, (size, bar, line, inside, outside)
    group = extent({"children": [find(login, "Group_ServerList")]})
    inside, outside = differing(shots["realms"][0], waiting, [(0, 0, group[2] - group[0] + 1, group[3] - group[1] + 1)])
    assert inside > 1000 and outside == 0, (size, group, inside, outside)
    white = sum(1 for p in region(waiting, line) if p == b"\xff\xff\xff")
    white_at_rest = sum(1 for p in region(shots["login"][0], line) if p == b"\xff\xff\xff")
    assert white > 300 and white > 2 * white_at_rest, (size, line, white, white_at_rest)

    for n in (1, 2, 3):
        _, _, boxes = shots[f"select-{n}"]
        assert [k for k, _ in boxes] == ["hall"] * n, (size, n, boxes)
        for _, (x0, y0, x1, y1) in boxes:
            assert 0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height, (size, n, boxes)

    path, _, boxes = shots["create"]
    assert [k for k, _ in boxes] == ["create"], (size, boxes)
    x0, y0, x1, y1 = boxes[0][1]
    assert y1 - y0 > 1.5 * (x1 - x0), (size, boxes)
    seams = seam_columns(path, width, origins["create"])
    assert seams == 0, (size, seams)
    root = LAYOUTS["create"]
    cx = int((width - (root["rect"][2] - root["rect"][0])) / 2)
    cy = int((height - (root["rect"][3] - root["rect"][1])) / 2)
    for ident, (image, down, on) in DOWN.items():
        drawn = region(path, (cx + image[0] - root["rect"][0], cy + image[1] - root["rect"][1],
                              cx + image[2] - root["rect"][0], cy + image[3] - root["rect"][1]))
        share = [sum(a == b for a, b in zip(drawn, tile)) / len(tile) for tile in (down, on)]
        # The rest lie under the button's label, drawn over it in every state.
        assert share[0] > 0.85 and share[1] < 0.5, (size, ident, share)
    for ident, (image, tile) in NORMAL.items():
        drawn = region(path, (cx + image[0] - root["rect"][0], cy + image[1] - root["rect"][1],
                              cx + image[2] - root["rect"][0], cy + image[3] - root["rect"][1]))
        share = sum(a == b for a, b in zip(drawn, tile)) / len(tile)
        # The rest lie under the button's label, a root string over it.
        assert share > 0.85, (size, ident, share)
    for ident, (image, tile) in CLASS_IMAGES.items():
        drawn = region(path, (cx + image[0] - root["rect"][0], cy + image[1] - root["rect"][1],
                              cx + image[2] - root["rect"][0], cy + image[3] - root["rect"][1]))
        share = sum(a == b for a, b in zip(drawn, tile)) / len(tile)
        # The rest lie under the class's label (root strings drawn after the
        # images) or are the image's 16 translucent corner pixels.
        assert share > 0.85, (size, ident, share)
    for ident, label in STAT_LABELS.items():
        pink, light = pink_and_light(region(path, (cx + label[0] - root["rect"][0], cy + label[1] - root["rect"][1],
                                                   cx + label[2] - root["rect"][0], cy + label[3] - root["rect"][1])))
        if ident in SHOWN_STATS:
            assert pink > 100 and light == 0, (size, ident, pink, light)
        else:
            assert pink == 0 and light > 100, (size, ident, pink, light)

    start, rect, _ = shots["loading-start"]
    world = shots["loading-world"][0]
    share = lit_share(start, rect), lit_share(world, rect)
    assert 0.5 < share[0] < 0.8 and share[1] > 0.95, (size, rect, share)

    path, rect, _ = shots["message"]
    assert len(set(region(path, rect))) > 10, (size, rect)
    titled, title, _ = shots["message-titled"]
    _, _, a = pixels(path)
    _, _, b = pixels(titled)
    inside = outside = 0
    if not titled_create:
        # A recipe that leaves a refused create untitled draws the two alike.
        assert a == b, (size, "an untitled message drew a title")
    # The glyphs may stand a few pixels past the 1264 layout's short title
    # rect (17 px at 1280x1024; KO's strings are not clipped to it).
    margin = 8
    for i in range(0, len(a), 3):
        if a[i:i + 3] != b[i:i + 3]:
            x, y = (i // 3) % width, (i // 3) // width
            if title[0] - margin <= x < title[2] + margin and title[1] - margin <= y < title[3] + margin:
                inside += 1
            else:
                outside += 1
    assert (inside > 20 if titled_create else inside == 0) and outside == 0, (size, title, inside, outside)

    # RQ-101: the logo screen. Each group's art is its layout's image that is
    # not the full-canvas black backdrop; the frame is black outside it.
    ox, oy, s = origins["logo-0"]
    arts = []
    for group in LOGO_GROUPS:
        x0, y0, x1, y1 = next(c["rect"] for c in group["children"] if c["rect"] != [0, 0, 1024, 768])
        arts.append((int(ox + x0 * s), int(oy + y0 * s), int(ox + x1 * s) + 1, int(oy + y1 * s) + 1))
    brightness = []
    for g, art in enumerate(arts):
        path, rect, boxes = shots["logo-%d" % g]
        assert boxes == [] and rect == (int(ox), int(oy), int(ox + 1024 * s), int(oy + 768 * s)), (size, rect)
        inside = region(path, art)
        # The art is drawn (group 1's grey "presents" has 16 colours as cooked).
        lit_art = sum(1 for p in inside if p != b"\0\0\0") / len(inside)
        assert len(set(inside)) > 10 and lit_art > 0.05, (size, g, len(set(inside)), lit_art)
        brightness.append(sum(sum(p) for p in inside) / len(inside))
        _, _, body = pixels(path)
        lit = sum(1 for i in range(0, len(body), 3) if body[i:i + 3] != b"\0\0\0"
                  and not (art[0] <= (i // 3) % width < art[2] and art[1] <= (i // 3) // width < art[3]))
        assert lit == 0, (size, g, lit)
    faded = region(shots["logo-fade"][0], arts[0])
    ratio = sum(sum(p) for p in faded) / len(faded) / brightness[0]
    assert 0.45 < ratio < 0.53, (size, ratio)
    logo = re.search(r"^FRONT_LOGO (.*)$", run.stdout, re.M)
    assert logo and logo.group(1) == ("groups=3 length=12 skip=1 cursor=1 alpha=1.000000,1.000000,1.000000,0.498039 "
                                      "before=logo end=login"), (size, logo and logo.group(1))

    music = re.search(r"^FRONT_MUSIC (.*)$", run.stdout, re.M)
    assert music and music.group(1) == ("login=0 realms=0 select=1 create=1 loading=none logo=2 delay=1 "
                                        "fade_group=2 fade=4"), (size, music)
    streams = {}
    for m in re.finditer(r"^FRONT_MUSIC_STREAM track=(\d+) kind=(\S+) rate=(\d+) channels=(\d+) frames=(\d+) "
                         r"loop=(\d) restart=(\S+) decoded=(\d+) restarts=(\d+) peak=(\S+) audible=(\d+) "
                         r"ended=(\d)$", run.stdout, re.M):
        streams[int(m.group(1))] = m
    assert sorted(streams) == [0, 1, 2], (size, run.stdout[-2000:])
    # The login track (sound 35): restarted at 21.66 s, before its own end
    # (21.667 s), so once in the pass and a second past it.
    kind, rate, channels, frames, loop, restart, decoded, restarts, peak, audible, ended = streams[0].groups()[1:]
    assert (kind, rate, channels, frames, loop, restart) == ("pcm", "22050", "2", "477749", "0", "21.66"), \
        streams[0].group(0)
    assert restarts == "1" and ended == "0" and int(decoded) > int(frames), streams[0].group(0)
    assert float(peak) > 0.1 and int(audible) > 48000 * 20, streams[0].group(0)
    # The select and create track (sound 20003): looped one second past its end.
    kind, rate, channels, frames, loop, restart, decoded, restarts, peak, audible, ended = streams[1].groups()[1:]
    assert (kind, rate, channels, frames, loop, restart) == ("pcm", "22050", "2", "3995263", "1", "0"), \
        streams[1].group(0)
    assert restarts == "0" and ended == "0" and int(decoded) > int(frames), streams[1].group(0)
    assert float(peak) > 0.1 and int(audible) > 48000 * 170, streams[1].group(0)
    # The logo's track (1264's Snd\\bless.wav, 005fa500): played once, to its end.
    kind, rate, channels, frames, loop, restart, decoded, restarts, peak, audible, ended = streams[2].groups()[1:]
    assert (kind, rate, channels, frames, loop, restart) == ("pcm", "22050", "1", "305280", "0", "0"), \
        streams[2].group(0)
    assert restarts == "0" and ended == "1" and decoded == frames, streams[2].group(0)
    assert float(peak) > 0.1 and int(audible) > 48000 * 13, streams[2].group(0)
    frames = "%s, %s and %s" % (streams[0].group(5), streams[1].group(5), streams[2].group(5))
    print(f"PASS front-end captures {size}: every screen unscaled where 1264 places it, "
          f"intro box {shots['login'][2][0][1]}, "
          f"realm name {realm_name} px in the list, the copyright line at {line[:2]} ({white} white px) "
          f"instead of the bar while a login waits and on the realm list (neither after a Back), 1-3 characters in the hall, create stands "
          f"{x1 - x0}x{y1 - y0} with no seams, loading {share[0]:.2f} -> {share[1]:.2f}, the logo's three "
          f"groups (faded {ratio:.2f}), music {frames} PCM frames, restarted, looped and played once; "
          f"the select's Exit and ESC ask yes or no in its box at {exit_box}, ESC and No closing it, ENTER and Yes "
          f"leaving; Back lands on the realm list")

# RQ-109 (KO-FINDINGS 9.6): the 1298 recipe's select is 1298's own bar,
# co_CharacterSelect_us.uif, placed as its Load (00606c10) places it, its
# nodes bound as its ReceiveMessage (00607160) and info fill (006074c0) use
# them. The chosen package with the 1298 cook as its front-end.bin (its
# release index rewritten; no server reads it here) draws it at KO's sizes.


def repack(base, front_end, into):
    """A copy of package `base` with `front_end` as its front-end.bin and its
    release index (tools/assetc/main.py's N3R1: each file's name, size and
    sha256) rewritten; the other files linked where the file system allows."""
    import hashlib
    import shutil
    if into.exists():
        shutil.rmtree(into)
    into.mkdir(parents=True)
    index = (base / "release.bin").read_bytes()
    data = front_end.read_bytes()
    at = 4 + 12
    for _ in range(2):
        at += 4 + struct.unpack_from("<I", index, at)[0]
    head, files, at = index[:at + 4], struct.unpack_from("<I", index, at)[0], at + 4
    entries = b""
    for _ in range(files):
        length = struct.unpack_from("<I", index, at)[0]
        name = index[at + 4:at + 4 + length].decode()
        end = at + 4 + length + 4 + 32
        if name == "front-end.bin":
            entries += index[at:at + 4 + length] + struct.pack("<I", len(data)) + hashlib.sha256(data).digest()
            shutil.copyfile(front_end, into / name)
        else:
            entries += index[at:end]
            try:
                os.link(base / name, into / name)
            except OSError:
                shutil.copyfile(base / name, into / name)
        at = end
    assert at == len(index), (at, len(index))
    (into / "release.bin").write_bytes(head + entries)
    (into / "release.sha256").write_text(hashlib.sha256(head + entries).hexdigest() + "\n")
    return into


package_1298 = repack(package, front_end_1298, B / "package-1298")
# RQ-114 (KO-FINDINGS 9.6, 9.14): btn_create from slot 1 with slots 0 and 1
# taken flies the camera to slot 2 by 1298's path 6 (005ff920, 005fa670),
# ka_left_right, which neither ENTER nor ESC skips; the camera is on the slot
# a tick after the path's last frame (005fe5b0 case 6). RQ-125 (KO-FINDINGS
# 9.15): create is a window of 1298's select (+0x388), shown with the click
# over the hall while the camera flies behind it (005ff920, Render 005fb1c0);
# the new character stands at the slot once the camera is there (state 7);
# ESC there, and one frame into the flight, returns to the select at rest on
# slot 2 with the bar shown (Cancel 005ffb90). The capture's frames are 0.25 s
# apart: the first after the click takes two steps of 7.5 frames (the load's
# and the tick's), each later one one.
fly_index = next(i for i, p in enumerate(recipe_1298["select"]["paths"]) if p.get("from") == 1 and p["to"] == 2)
assert recipe_1298["select"]["paths"][fly_index]["path"].endswith("ka_left_right_camera.n3camera"), fly_index
assert any(p.get("from") == 2 and p["to"] == 1 and p["path"].endswith("ka_right_left_camera.n3camera")
           for p in recipe_1298["select"]["paths"]), recipe_1298["select"]["paths"]
fly_rate, fly_eye, fly_at_rate, fly_at = ko_front_end.camera_path(pinned, recipe_1298["select"]["paths"][fly_index]["path"])


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


# The path's last frame as the client works it out in floats (select_path.h
# path_frames, 1298's 0043b480: count x rate x 1/30), then the draws: the
# first after the click two steps, one each later, until a draw starts on the
# last frame.
fly_frames = max(f32(f32(len(keys) * rate) * f32(1 / 30)) for keys, rate in ((fly_eye, fly_rate), (fly_at, fly_at_rate)))
fly_draws, frame = 1, f32(f32(0 + 7.5) + 7.5)
while frame != fly_frames:
    frame, fly_draws = min(fly_frames, f32(frame + 7.5)), fly_draws + 1
# RQ-130 (KO-FINDINGS 9.15): no new character on the arrival until the race
# is clicked, then at the slot the camera is on, its button drawn down (state
# 1); the race clicked one frame into a flight stands at slot 1, the slot the
# flight left (005fd120 by +0x38c), once the camera is on slot 2.
CREATE_FLY = (f"click=create path={fly_index} frames={fly_frames:.6g} slot=1 focus=2 new=0 arrived=2 "
              f"draws={fly_draws + 1} new=0 race=1 new=1 figure=2 back=select slot=2 cancel=select slot=2 ui=1 "
              f"flown=1 new=1")
# RQ-130: create opened at rest: no character and both buttons normal; Create
# says create_name (empty), then create_no_race (a class clicked first too),
# then, a race click having unchosen the class, create_no_class; with both
# clicked it sends. A chosen button draws down under the pointer.
# RQ-133 (KO-FINDINGS 9.15): the recipe's until-race nodes, in the layout's
# order, draw at each open and after a class click, none once the race is
# clicked (006060f0(2) hides the warrior and mage buttons and the rogue and
# priest images), and all again after a Cancel and a new open (006066b0).
UNTIL_1298 = "img_rogue,img_priest,btn_class_warrior,btn_class_mage"
assert sorted(UNTIL_1298.split(",")) == sorted(recipe_1298["screens"]["create"]["until_race"]), recipe_1298
CREATE_CHOICE = (f"open=0,0,0 until={UNTIL_1298} empty=create_name norace=create_no_race class=1,0 "
                 f"until={UNTIL_1298} classfirst=create_no_race race=1,0,1 until=- noclass=create_no_class "
                 f"both=1,1,1 create=none sent=1 reopen={UNTIL_1298}")
# RQ-125: 1298's in-select create, co_characterCreate_us.uif (row 2's, as
# 005fab40 loads it), its root at the origin and its panels where its Tick
# (00606450) clamps their slides: Group_class at (50, H - 30 - h), Group_race at
# (W - w - 50, H - 30 - h), Group_name centred at H - 30 - h.
create_tree = ko_hud.parse(pinned.get(recipe_1298["screens"]["create"]["ui"]))
assert recipe_1298["screens"]["create"]["ui"] == "UI_US/co_characterCreate_us.uif", recipe_1298["screens"]["create"]
bar_tree = ko_hud.parse(pinned.get(recipe_1298["screens"]["select"]["ui"]))
bar_w = bar_tree["rect"][2] - bar_tree["rect"][0]
bar_h = bar_tree["rect"][3] - bar_tree["rect"][1]
# RQ-111: the 1298 recipe's message box, El_MessageBox_us.uif (005282a0's).
box_tree = ko_hud.parse(pinned.get(recipe_1298["screens"]["message"]["ui"]))
BAR = {"select_prev": "btn_left", "select_next": "btn_right", "back": "btn_back", "exit": "btn_exit",
       "select_start": "btn_start", "select_create": "btn_create", "select_delete": "btn_delete",
       "char_name": "str_id", "char_level": "str_lev", "char_class": "str_job"}
for size in ("1024x768", "1280x1024", "1600x1200"):
    width, height = map(int, size.split("x"))
    run = subprocess.run(["build/client/n3e-test-client", str(package_1298), "--realm", str(realm),
                          "--fixed-window", size],
                         capture_output=True, text=True, timeout=600,
                         env={**os.environ, "N3E_TEST_FRONT_END": str(B / ("1298-" + size))})
    (B / f"client-1298-{size}.log").write_text(run.stdout + run.stderr)
    assert run.returncode == 0 and "FRONT_SHOTS done" in run.stdout, (size, run.stdout[-2000:], run.stderr[-2000:])
    shots = {m.group(1): (Path(m.group(2)), m.group(3)) for m in re.finditer(
        r"^FRONT_SHOT name=(\S+) size=\S+ path=(\S+) rect=(\S*) drawn=\S* origin=\S+,\S+,1$", run.stdout, re.M)}
    assert {"select-0", "select-1", "select-3"} <= set(shots), (size, sorted(shots))
    # The bar's root at ((W - w) >> 1, H - 10 - h), each node carried with it.
    x0, y0 = (width - bar_w) >> 1, height - 10 - bar_h
    want = {}
    for action, ident in BAR.items():
        r = find(bar_tree, ident)["rect"]
        want[action] = (x0 + r[0] - bar_tree["rect"][0], y0 + r[1] - bar_tree["rect"][1],
                        x0 + r[2] - bar_tree["rect"][0], y0 + r[3] - bar_tree["rect"][1])
    got = {}
    for line in ("FRONT_PLACED", "FRONT_SELECT_BAR"):
        found = re.search(r"^%s (.*)$" % line, run.stdout, re.M)
        assert found, (size, line)
        got.update({k: tuple(map(int, v.split(","))) for k, v in re.findall(r"(\w+)=(\S+)", found.group(1))})
    assert got == want, (size, {k: (got.get(k), v) for k, v in want.items() if got.get(k) != v})
    # RQ-113 (KO-FINDINGS 9.6): 1298 never hides an arrow, so both draw at
    # each end of the row (select.arrows draw).
    arrows = re.search(r"^FRONT_ARROWS (.*)$", run.stdout, re.M)
    assert arrows and arrows.group(1) == "left=1,1 right=1,1", (size, arrows and arrows.group(1))
    # The bar's art is drawn there: its three backdrop images span it.
    art = region(shots["select-1"][0], (x0, y0 + 2, x0 + bar_w, y0 + bar_h - 2))
    assert len(set(art)) > 50 and sum(p == b"\0\0\0" for p in art) < len(art) // 20, (size, len(set(art)))
    # The info texts: empty with no character, the character's name, level
    # and class with one (pixels differ inside each text's rect).
    margin = 4
    for action in ("char_name", "char_level", "char_class"):
        r = want[action]
        inside, _ = differing(shots["select-0"][0], shots["select-1"][0],
                              [(r[0] - margin, r[1] - margin, r[2] + margin, r[3] + margin)])
        assert inside > 20, (size, action, inside)
    # RQ-111 (KO-FINDINGS 9.7): Exit asks row 1502 with Yes and No, as
    # 00607160 posts it (MB_YESNO, BEHAVIOR_EXIT), in the box 005282a0 loads
    # and centres; ESC and No close it, ENTER and Yes leave. RQ-119
    # (KO-FINDINGS 9.9): ESC on the select at rest does nothing, as 1298's bar
    # OnKeyPress (00607810) presses no button for it.
    assert {"message", "message-exit"} <= set(shots), (size, sorted(shots))
    bx, by = check_exit(size, run.stdout, box_tree, width, height, shots["message"][0], shots["message-exit"][0],
                        tuple(map(int, shots["message-exit"][1].split(","))), "none", "realms")
    flight = re.search(r"^FRONT_CREATE (.*)$", run.stdout, re.M)
    assert flight and flight.group(1) == CREATE_FLY, (size, flight and flight.group(1), CREATE_FLY)
    # RQ-125: the create shot (no character, slot 0 in focus) over the hall:
    # the name entry where Group_name's slide clamps, no character drawn (none
    # listed, and RQ-130: no race clicked yet), and the hall drawn between the
    # panels (the zone's terrain, not the black clear).
    created = re.search(r"^FRONT_SHOT name=create size=\S+ path=(\S+) rect=(\S+) drawn=(\S*) origin=", run.stdout, re.M)
    assert created, size
    group_name, edit = find(create_tree, "Group_name"), find(create_tree, "edit_name")
    nx0, ny0 = (width - (group_name["rect"][2] - group_name["rect"][0])) // 2, \
        height - 30 - (group_name["rect"][3] - group_name["rect"][1])
    want_edit = (nx0 + edit["rect"][0] - group_name["rect"][0], ny0 + edit["rect"][1] - group_name["rect"][1],
                 nx0 + edit["rect"][2] - group_name["rect"][0], ny0 + edit["rect"][3] - group_name["rect"][1])
    assert tuple(map(int, created.group(2).split(","))) == want_edit, (size, created.group(2), want_edit)
    # RQ-130: 1298's create opens with no race chosen, so no new character.
    kinds = [d.split(":")[0] for d in created.group(3).split(";") if d]
    assert kinds == [], (size, created.group(3))
    race_w = find(create_tree, "Group_race")["rect"][2] - find(create_tree, "Group_race")["rect"][0]
    class_w = find(create_tree, "Group_class")["rect"][2] - find(create_tree, "Group_class")["rect"][0]
    between = region(Path(created.group(1)), (50 + class_w + 4, height // 2, width - race_w - 54, ny0 - 4))
    lit = sum(p != b"\0\0\0" for p in between)
    assert lit > len(between) // 2, (size, lit, len(between))
    # RQ-126: create's slide, frame by frame as 1298's Tick moves the panels.
    slid = re.search(r"^FRONT_CREATE_SLIDE screen=(\S+) frames=(\S+) on=(\d)$", run.stdout, re.M)
    assert slid and slid.group(1) == "create" and slid.group(3) == "0", (size, slid and slid.group(0)[:200])
    slide_frames = [tuple(map(int, frame.split(","))) for frame in slid.group(2).split(";")]
    want_slide = ko_create_slide(create_tree, width, height, 1 / 32)
    assert slide_frames == want_slide, (size, slide_frames[-3:], want_slide[-3:])
    # RQ-130: the race and class wait for their clicks; the refusals in 1298's words.
    choice = re.search(r"^FRONT_CREATE_CHOICE (.*)$", run.stdout, re.M)
    assert choice and choice.group(1) == CREATE_CHOICE, (size, choice and choice.group(1), CREATE_CHOICE)
    boxes = re.findall(r"^FRONT_CREATE_MESSAGE (.*)$", run.stdout, re.M)
    assert boxes == [choice_boxes[0], choice_boxes[0], choice_boxes[1]], (size, boxes, choice_boxes)
    print(f"PASS front-end captures 1298 recipe {size}: 1298's select bar at ({x0}, {y0}), unscaled, its ten "
          f"bound nodes where 1298's Load puts them, its info texts filled for a character and empty without; "
          f"its Exit asks yes or no in its centred box at ({bx}, {by}), ESC and No closing it, ENTER and Yes leaving the game; "
          f"ESC on the select does nothing; Back lands on the realm list; Create from an occupied slot opens "
          f"1298's in-select create over the hall at once, the camera flying behind it to the first empty slot "
          f"on ka_left_right ({fly_frames:.6g} frames, not skipped), the new character standing there on the "
          f"camera's arrival and the "
          f"race click; Cancel returns to the select at rest on that slot; its panels slide in as 1298's Tick "
          f"moves them ({len(slide_frames)} frames at 32 a second, Group_class ending at "
          f"{slide_frames[-1][2]}, Group_name at {slide_frames[-1][5]}); it waits for its race and class, "
          f"Create saying rows 1908 and 1904 under 1901 until both are clicked")
print("PASS KO front end graphical")
