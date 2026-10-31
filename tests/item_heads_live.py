"""PQ-354 (D-194): item tooltip heads (item-heads.bin, N3IH), live.

The rule is the 2233 client's tooltip head (005aa8e0): the name line in its
attribute's colour, the kind line under it in its own colour, both centred,
and "<selfname>" in the name replaced by the player's own name (004aad90).
n3e carries it as package data: per item a name colour and head lines, and a
package token the client replaces with the viewer's character name. Evidence:
docs/implementation/evidence/pq-354-item-tooltip-head-2233.md.

The package is the PQ-272 fixture (tests/npc_scale_live.py) with original
synthetic data: a minimal N3H7 HUD written here (a white font atlas whose
glyph cells are solid, so each drawn glyph is a 16 x 20 block of its line's
colour; the inventory button; bag slots; a tooltip background and rows), the
blade and the potion labelled "{me}'s Practice blade" and "{me}'s Practice
potion", and item heads with the token "{me}": the blade's name orange with
two head lines (cyan, violet), the potion without a head.

Both readers must accept the package and refuse malformed item-heads.bin
files. Against a native server on a disposable Postgres and Redis, an account
creates the character "Explorer". With N3E_GRAPHICAL=1 the real test client
logs in, opens the bag, hovers the blade and then the potion, and captures
each tooltip: the blade's rows are "Explorer's Practice blade" (orange,
centred) and its two head lines (centred) before its usual rows; the potion's
first row is "Explorer's Practice potion" in yellow with no head line; and in
the captures each line is drawn in its colour, at the substituted name's width,
the head lines centred under the name.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tests") not in sys.path:
    sys.path.append(str(ROOT / "tests"))
from isolation import once_per_run  # noqa: E402
import npc_looks_live  # noqa: E402
import tooltip_head  # noqa: E402

OUT = ROOT / "build/pq354"
TOKEN = "{me}"
NAME, KIND, SECOND = 0xFF8020, 0x20C0FF, 0xC040FF
HEADS = {"self_token": TOKEN, "items": [{"item": "demo:item/blade", "name_color": NAME, "lines": [
    {"text": "(Synthetic kind)", "color": KIND}, {"text": "Second head line", "color": SECOND}]}]}
LABELS = {"demo:item/blade": TOKEN + "'s Practice blade", "demo:item/potion": TOKEN + "'s Practice potion"}
CHARACTER = "Explorer"
ADVANCE, GLYPH = 16, (16, 20)  # font advance, glyph quad (client/render/presentation.h)
ROWS = [(8 + 22 * i, 28 + 22 * i) for i in range(10)]  # tooltip rows, 20 px apart by 2
BACKGROUND = (24, 24, 40)
WINDOW = (1024, 768)  # HUD scale 1


def u(*xs):
    return b"".join(struct.pack("<I", x) for x in xs)


def f(*xs):
    return struct.pack("<%df" % len(xs), *xs)


def string(text):
    return u(len(text)) + text.encode("ascii")


def record(kind, rect, binding, text, panel, texture=0):
    """One N3H7 record: kind, anchor, rect, texture, uv, binding, text, colour,
    target, align, control, states, text flags, panel (client/assets/assets.cpp
    load_hud)."""
    return (u(kind) + f(0, 0) + f(*rect) + u(texture) + f(0, 0, 1, 1) + string(binding) + string(text)
            + u(0xFFFFFFFF) + u(0, 0) + u(0, 15, 0) + u(panel))


def hud(npc_health, level_xp):
    font = (256, 128, bytes([255]) * (256 * 128 * 4))
    background = (4, 4, bytes(BACKGROUND + (255,)) * 16)
    textures = [font, background]
    data = b"N3H7" + u(0) + f(npc_health, level_xp) + u(len(textures))
    data += b"".join(u(w) + u(h) + pixels for w, h, pixels in textures)
    data += f(ADVANCE) + u(GLYPH[1], 0) + u(0)  # font metrics; no controls
    records = [record(2, (900, 700, 1000, 740), "action", "inventory", 0)]
    for i in range(4):  # the bag: slots 0-3 on the inventory panel (1)
        rect = (80 + 60 * i, 600, 130 + 60 * i, 650)
        records += [record(0, rect, "item", "bag:%d" % i, 1), record(2, rect, "action", "bag:%d" % i, 1)]
    data += u(len(records)) + b"".join(records)
    data += u(0) + u(0)  # no item icons, no portraits
    # The tooltip: background texture 1, padding 16 x 16, gap 26, the rows.
    data += u(1) + f(0, 0, 1, 1) + f(16, 16, 26) + u(len(ROWS)) + b"".join(f(*r) for r in ROWS)
    return data


@once_per_run
def prepare():
    """Cook the PQ-272 package with the HUD, labels and item heads; returns it."""
    from npc_scale_live import prepare as base
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    import main

    source = base().parent / "source"
    root, out = OUT / "source", OUT / "package"
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(source, root)
    m = json.loads((root / "package.json").read_text())
    assert m["engine_version"] >= 33 and "presentation" in m and "item_heads" not in m
    for item in m["inventory"]["items"]:
        item["label"] = LABELS.get(item["id"], item["label"])
    assert {i["id"] for i in m["inventory"]["items"]} >= set(LABELS)
    m["item_heads"] = HEADS
    (root / m["presentation"]["hud.bin"]).write_bytes(hud(m["gameplay"]["npc_health"], m["gameplay"]["level_xp"]))
    (root / "package.json").write_text(json.dumps(m))
    main.cook(root, out)
    return out.resolve()


def repack(package, out, data):
    """A copy of `package` whose item-heads.bin is `data` (None: removed),
    rehashed into release.bin."""
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(package, out)
    if data is None:
        (out / "item-heads.bin").unlink()
    else:
        (out / "item-heads.bin").write_bytes(data)
    m = json.loads((out / "recipe.json").read_text())["manifest"]
    names = sorted(p.name for p in out.iterdir() if p.name not in ("release.bin", "release.sha256"))
    index = b"N3R1" + u(1, m["engine_version"], m["protocol_version"]) + string(m["game_id"]) \
        + string(m["package_version"]) + u(len(names))
    for name in names:
        data = (out / name).read_bytes()
        index += string(name) + u(len(data)) + hashlib.sha256(data).digest()
    (out / "release.bin").write_bytes(index)


def readers(package):
    """The client's and the server's verdicts on `package` (True: accepted)."""
    verdict = []
    for cmd in [["build/client/n3e-asset-check", str(package)], ["target/debug/n3e-server", "--check-content"]]:
        p = subprocess.run(cmd, cwd=ROOT, env={**os.environ, "N3E_PACKAGE": str(package)}, capture_output=True,
                           text=True)
        verdict.append(p.returncode == 0)
    return verdict


def check_readers(package):
    npc_looks_live.check_readers(package)
    good = (package / "item-heads.bin").read_bytes()
    blade = string("demo:item/blade")
    heads = lambda *body: b"N3IH" + string(TOKEN) + u(len(body)) + b"".join(body)  # noqa: E731
    cases = {
        "magic": b"N3IJ" + good[4:],
        "trailing": good + b"\0",
        "truncated": good[:-1],
        "nothing": b"N3IH" + u(0, 0),
        "token space": b"N3IH" + string("{m e}") + u(0),
        "undefined item": heads(string("demo:item/sword") + u(0, 0)),
        "twice": heads(blade + u(0, 0), blade + u(0, 0)),
        "name colour": heads(blade + u(0x1000000, 0)),
        "five lines": heads(blade + u(0, 5) + (string("x") + u(0)) * 5),
        "control byte": heads(blade + u(0, 1) + string("a\tb") + u(0)),
        "line colour": heads(blade + u(0, 1) + string("x") + u(0x1000000)),
    }
    bad = OUT / "hostile"
    for name, data in cases.items():
        repack(package, bad, data)
        assert readers(bad) == [False, False], (name, readers(bad))
    # Without the file the package reads as before (both readers accept it).
    repack(package, bad, None)
    assert readers(bad) == [True, True]
    shutil.rmtree(bad)
    return len(cases)


def runs(path, colour, tolerance=3, within=None):
    """The pixels of `colour` (0xRRGGBB, each channel within `tolerance`) in a
    capture (or in its box `within`), as (count, (x0, y0, x1, y1)), x1 / y1
    exclusive."""
    width, height, pixels = npc_looks_live.read_ppm(path)
    want = (colour >> 16 & 255, colour >> 8 & 255, colour & 255)
    x0, y0, x1, y1 = within or (0, 0, width, height)
    xs, ys, count = [], [], 0
    for y in range(y0, y1):
        row = pixels[y * width * 3:(y + 1) * width * 3]
        for x in range(x0, x1):
            if all(abs(row[3 * x + c] - want[c]) <= tolerance for c in range(3)):
                xs.append(x)
                ys.append(y)
                count += 1
    return (count, (min(xs), min(ys), max(xs) + 1, max(ys) + 1)) if count else (0, None)


def line_box(path, colour, text, within):
    """The drawn line of `text` in `colour` inside the tooltip `within`: its box
    must be the solid glyph run of exactly len(text) glyphs (one 16 x 20 block
    each, ADVANCE apart)."""
    count, box = runs(path, colour, within=within)
    width = (len(text) - 1) * ADVANCE + GLYPH[0]
    assert box and box[2] - box[0] == width and box[3] - box[1] == GLYPH[1], (text, hex(colour), count, box, width)
    assert count >= .98 * width * GLYPH[1], (text, hex(colour), count, box)
    return box


def live(package):
    from isolation import DISPOSABLE_POSTGRES, container_logs, free_ports
    from readiness import wait_postgres
    from world_peer import Peer
    import urllib.request

    manifest = json.loads((package / "recipe.json").read_text())["manifest"]
    out = OUT / "live"
    out.mkdir(parents=True, exist_ok=True)
    server_binary = str(Path(os.environ.get("N3E_TEST_SERVER", "target/debug/n3e-server")).resolve())
    name = "n3e-pq354-" + uuid.uuid4().hex[:10]
    password = "test-only-" + uuid.uuid4().hex
    containers, server, log = [], None, None

    def run(*cmd, env=None, stdin=None):
        p = subprocess.run(cmd, env=env, input=stdin, capture_output=True, text=True, timeout=120)
        assert p.returncode == 0, (cmd, p.returncode, p.stdout, p.stderr)
        return p.stdout

    try:
        for suffix, image, port, extra in [
            ("", npc_looks_live.POSTGRES, 5432, ["-e", "POSTGRES_USER=n3e", "-e", "POSTGRES_PASSWORD=test-only",
                                                 "-e", "POSTGRES_DB=n3e", *DISPOSABLE_POSTGRES]),
            ("-redis", npc_looks_live.REDIS, 6379, []),
        ]:
            run("docker", "run", "--rm", "-d", "--name", name + suffix, *extra, "-p", f"127.0.0.1::{port}", image)
            containers.append(name + suffix)
        pg = wait_postgres(name)
        redis = run("docker", "port", name + "-redis", "6379").split()[0]
        listen, health = free_ports(2)
        env = dict(os.environ, DATABASE_URL=f"host=127.0.0.1 port={pg} user=n3e password=test-only dbname=n3e",
                   REDIS_ADDRESS=redis, N3E_PACKAGE=str(package), N3E_REALM="test-" + name,
                   N3E_LISTEN=f"127.0.0.1:{listen}", N3E_HEALTH=f"127.0.0.1:{health}")
        run(server_binary, "migrate", env=env)
        run(server_binary, "convert-progression", env={**env, "N3E_TEST_PROGRESSION": "disposable"})
        run(server_binary, "account-create", "explorer", env=env, stdin=password + "\n")
        log = open(out / "server.log", "w")
        server = subprocess.Popen([server_binary], env=env, stdout=log, stderr=log)
        deadline = time.monotonic() + 30
        while True:
            assert server.poll() is None, (out / "server.log").read_text()[-2000:]
            assert time.monotonic() < deadline, "server never reported ready"
            try:
                if urllib.request.urlopen(f"http://127.0.0.1:{health}/ready", timeout=0.2).status == 200:
                    break
            except OSError:
                time.sleep(0.1)
        p = Peer(listen, "explorer", password, content=(package / "release.sha256").read_text().strip(),
                 game=manifest["game_id"], protocol=manifest["protocol_version"])
        p.create(CHARACTER)
        assert p.select(p.characters[0][0])[0] == 10
        p.logout()
        print(f"PASS the server admits the N3IH package (it checks item-heads.bin and otherwise ignores it); "
              f"the character {CHARACTER} is created over the wire", flush=True)
        if os.environ.get("N3E_GRAPHICAL") != "1":
            return

        def client(role, item):
            capture = out / role
            with tempfile.TemporaryDirectory(dir=OUT) as config:
                proc = subprocess.Popen(
                    ["build/client/n3e-test-client", str(package), "--connect", f"localhost:{listen}", "--ca",
                     "deploy/local/ca.pem", "--auto-login", "--fixed-window", "%dx%d" % WINDOW,
                     "--world-smoke", "60", "--capture", str(capture)],
                    env={**os.environ, "N3E_TEST_ACCOUNT": "explorer", "N3E_TEST_PASSWORD": password,
                         "N3E_TEST_ITEM_TOOLTIP": role, "N3E_TEST_ITEMS": f"{role}={item}",
                         "XDG_CONFIG_HOME": config},
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                lines = []
                reader = threading.Thread(target=lambda: lines.extend(proc.stdout), daemon=True)
                reader.start()
                proc.wait(timeout=180)
                reader.join(10)
            text = "".join(lines)
            capture.with_suffix(".log").write_text(text)
            assert proc.returncode == 0, (proc.returncode, text[-1500:])
            key = re.findall(r"^ITEM_SLOT key=(bag:\d+) item=%s icon=0 " % re.escape(item), text, re.M)
            assert len(key) == 1, text[-1500:]
            rows = re.findall(r"^ITEM_TOOLTIP key=%s row=(\d+) text=(.*)$" % key[0], text, re.M)
            styles = re.findall(r"^ITEM_TOOLTIP_STYLE key=%s row=(\d+) color=([0-9a-f]{6}) centred=([01])$"
                                % key[0], text, re.M)
            assert rows and len(styles) == len(rows), (rows, styles)
            shot = Path(f"{capture}.item-tooltip.ppm")
            return [(t, int(c, 16), c2 == "1") for (_, t), (_, c, c2) in zip(rows, styles)], shot, text, key[0]

        def tooltip(shot):
            """The tooltip's box: where its background texel is drawn."""
            count, box = runs(shot, (BACKGROUND[0] << 16) | (BACKGROUND[1] << 8) | BACKGROUND[2], tolerance=1)
            assert count > 1000, (count, box)
            return box

        blade, shot, text, key = client("blade", "demo:item/blade")
        label = f"{CHARACTER}'s Practice blade"
        assert blade[:3] == [(label, NAME, True), ("(Synthetic kind)", KIND, True),
                             ("Second head line", SECOND, True)], blade
        assert len(blade) > 3 and not blade[3][2] and not blade[3][0].startswith(("(", "Second")), blade
        box = tooltip(shot)
        boxes = [line_box(shot, c, t, box) for t, c, _ in blade[:3]]
        centre = [(b[0] + b[2]) / 2 for b in boxes]
        assert all(box[0] <= b[0] and b[2] <= box[2] and box[1] <= b[1] and b[3] <= box[3] for b in boxes), (box, boxes)
        assert max(centre) - min(centre) <= 1 and abs(centre[0] - (box[0] + box[2]) / 2) <= 1, (box, boxes)
        assert [b[1] - boxes[0][1] for b in boxes] == [r[0] - ROWS[0][0] for r in ROWS[:3]], boxes
        assert not runs(shot, 0xFFFF00, within=box)[0], "a yellow line in the blade's tooltip"
        # The client's own record of the drawn tooltip agrees (tests/tooltip_head.py).
        head, drawn = tooltip_head.check(text, key, shot, [(t, c) for t, c, _ in blade[:3]], least=300,
                                          base=Path(str(shot).replace("item-tooltip", "item-slot")))
        assert all(abs(x - b[0]) <= 1 and abs(y - b[1]) <= 1 for (x, y, _), b in zip(drawn["lines"], boxes)), drawn
        print(f"PASS graphical client draws the blade's tooltip head: {label!r} in {NAME:06x} ({TOKEN} replaced by "
              f"the character's name), then its two head lines in {KIND:06x} and {SECOND:06x}, each a solid glyph "
              f"run of its text's length centred at x={centre[0]:.0f} in the tooltip {box}, on rows "
              f"{[b[1] for b in boxes]}; {shot}", flush=True)
        potion, shot, text, key = client("potion", "demo:item/potion")
        label = f"{CHARACTER}'s Practice potion"
        assert potion[0] == (label, 0xFFFF00, True) and potion[1][0] == "Quantity: 5" and not potion[1][2], potion
        box = tooltip(shot)
        line_box(shot, 0xFFFF00, label, box)
        tooltip_head.check(text, key, shot, [(label, 0xFFFF00)], least=300,
                           base=Path(str(shot).replace("item-tooltip", "item-slot")))
        assert not any(runs(shot, c, within=box)[0] for c in (NAME, KIND, SECOND)), "a head colour in the potion's tooltip"
        print(f"PASS graphical client draws the item tooltip head: the potion (no head) keeps the yellow name "
              f"{label!r} with its token replaced and no head line; {shot}", flush=True)
    finally:
        if server is not None:
            server.kill()
            server.wait()
        if log is not None:
            log.close()
        for c in containers:
            container_logs({name: "postgres", name + "-redis": "redis"}[c], ["docker", "logs", "--timestamps", c])
        for c in containers:
            subprocess.run(["docker", "rm", "-f", c], capture_output=True)


if __name__ == "__main__":
    os.chdir(ROOT)
    package = prepare()
    assert (package / "item-heads.bin").read_bytes()[:4] == b"N3IH"
    refused = check_readers(package)
    print(f"PASS N3IH package: both readers accept it, and read it as before without the file; both refuse "
          f"{refused} malformed item-heads.bin files", flush=True)
    live(package)
