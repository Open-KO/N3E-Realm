"""Opt-in (make live-ko): spec 11 acceptance 5 and 6 on the Moradon package cooked
from the player's own KO data.

5. Each front end games/moradon offers (front-ends.json, RQ-078) cooks twice
   with identical bytes and the client loader (build/client/n3e-front-end-check)
   takes it (the 1097 choice's screens from the 1264 install, RQ-085); the one realm-config.json chooses is the bytes the package holds
   (the `moradon` prepare step's cook). The 1298 recipe, not offered yet
   (RQ-086), cooks the same way from the pinned tree with 1298's select
   character and camera paths (RQ-087), no hall and its select zone and fog
   (RQ-095), and the loader takes it.
6. The test client draws each screen at rest at 1280x1024 and 1024x768 (KO's sizes)
   (N3E_TEST_FRONT_END, client/harness/front_end_captures.inc) and this script
   checks the frames:
   - login: the intro character is drawn and its projected box covers the view's
     centre (KO's close-up runs past the frame's edges), and the login button's
     rect holds its art (not one flat colour);
   - realms: the list shows the realm's name: against the same frame with an
     unnamed realm, pixels differ inside the list's rect and nowhere else;
   - select: 1, 2 and 3 characters drawn, each box non-empty and inside the view;
   - create: the create model stands (KO's InitChr model breathing, not the hall's
     seated clip): its box is clearly taller than wide; and the stone background
     shows no seams (KO's UI point sampling on whole pixels): no column of a band
     across its top is darker than 0.6 of the band's mean;
   - loading: the progress bar's lit share grows from the start stage (2/3: the
     package and its textures) to the first World (1);
   - message: the box's text rect holds text (RQ-085: 1264's El_MessageBox_us,
     its OK button only, as KO's MessageBoxPost shows an MB_OK box);
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

No server or stack.
"""
import json
import os
import re
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
assert cooked[0] == cooked[1], "the 1298 recipe's cook is not deterministic"
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


def seam_columns(path, width, height):
    """Columns of the create screen's top stone band (canvas y 10-30, x 20-1000)
    darker than 0.6 of the band's mean: the black texels that border each of
    KO's tiles, blended in."""
    _, _, body = pixels(path)
    s = min(width / 1024, height / 768)
    ox, oy = (width - 1024 * s) / 2, (height - 768 * s) / 2
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

realm = B / "realm.json"
realm.write_text('{"id": "front-end", "name": "Local Realm", "host": "127.0.0.1", "port": 1, '
                 '"discord_client_id": "0"}')
for size in ("1280x1024", "1024x768"):
    width, height = map(int, size.split("x"))
    run = subprocess.run(["build/client/n3e-test-client", str(package), "--realm", str(realm),
                          "--fixed-window", size],
                         capture_output=True, text=True, timeout=600,
                         env={**os.environ, "N3E_TEST_FRONT_END": str(B / size)})
    (B / f"client-{size}.log").write_text(run.stdout + run.stderr)
    assert run.returncode == 0 and "FRONT_SHOTS done" in run.stdout, (size, run.stdout[-2000:], run.stderr[-2000:])
    shots = {}
    for m in re.finditer(r"^FRONT_SHOT name=(\S+) size=(\d+)x(\d+) path=(\S+) rect=(\S*) drawn=(\S*)$",
                         run.stdout, re.M):
        name, w, h, path, rect, drawn = m.groups()
        assert (int(w), int(h)) == (width, height), (size, m.group(0))
        boxes = [(kind, tuple(map(int, box.split(",")))) for kind, box in
                 (d.split(":") for d in drawn.split(";") if d)]
        shots[name] = (Path(path), tuple(map(int, rect.split(","))) if rect else None, boxes)
    assert set(shots) == {"login", "realms", "realms-unnamed", "select-1", "select-2", "select-3", "create",
                          "loading-start", "loading-world", "message", "logo-0", "logo-1", "logo-2",
                          "logo-fade"}, shots.keys()

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

    for n in (1, 2, 3):
        _, _, boxes = shots[f"select-{n}"]
        assert [k for k, _ in boxes] == ["hall"] * n, (size, n, boxes)
        for _, (x0, y0, x1, y1) in boxes:
            assert 0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height, (size, n, boxes)

    path, _, boxes = shots["create"]
    assert [k for k, _ in boxes] == ["create"], (size, boxes)
    x0, y0, x1, y1 = boxes[0][1]
    assert y1 - y0 > 1.5 * (x1 - x0), (size, boxes)
    seams = seam_columns(path, width, height)
    assert seams == 0, (size, seams)

    start, rect, _ = shots["loading-start"]
    world = shots["loading-world"][0]
    share = lit_share(start, rect), lit_share(world, rect)
    assert 0.5 < share[0] < 0.8 and share[1] > 0.95, (size, rect, share)

    path, rect, _ = shots["message"]
    assert len(set(region(path, rect))) > 10, (size, rect)

    # RQ-101: the logo screen. Each group's art is its layout's image that is
    # not the full-canvas black backdrop; the frame is black outside it.
    s = min(width / 1024, height / 768)
    ox, oy = (width - 1024 * s) / 2, (height - 768 * s) / 2
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
    print(f"PASS front-end captures {size}: intro box {boxes and shots['login'][2][0][1]}, "
          f"realm name {inside} px in the list, 1-3 characters in the hall, create stands "
          f"{x1 - x0}x{y1 - y0} with no seams, loading {share[0]:.2f} -> {share[1]:.2f}, the logo's three "
          f"groups (faded {ratio:.2f}), music {frames} PCM frames, restarted, looped and played once")
print("PASS KO front end graphical")
