"""Opt-in (make live-ko): spec 11 acceptance 5 and 6 on the Moradon package cooked
from the player's own KO data.

5. The front-end cook of the pinned tree runs twice with identical bytes, the same
   bytes the package holds (the `moradon` prepare step's cook).
6. The test client draws each screen at rest at 1280x800 and 1024x768
   (N3E_TEST_FRONT_END, client/harness/front_end_captures.inc) and this script
   checks the frames:
   - login: the intro character is drawn and its projected box covers the view's
     centre (KO's close-up runs past the frame's edges), and the login button's
     rect holds its art (not one flat colour);
   - realms: the list shows the realm's name: against the same frame with an
     unnamed realm, pixels differ inside the list's rect and nowhere else;
   - select: 1, 2 and 3 characters drawn, each box non-empty and inside the view;
   - loading: the progress bar's lit share grows from the start stage (2/3: the
     package and its textures) to the first World (1);
   - message: the box's text rect holds text.

No server or stack.
"""
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
import ko_character  # noqa: E402
import ko_front_end  # noqa: E402

cooked = []
for i in range(2):
    out = Path(tempfile.mkdtemp(prefix="front-end-", dir=B))
    ko_front_end.cook(ko_character.Assets(Path("assets/ko")), out, "games/moradon/front-end.json", out / "work")
    cooked.append((out / "front-end.bin").read_bytes())
assert cooked[0] == cooked[1], "the front-end cook is not deterministic"
assert cooked[0] == (package / "front-end.bin").read_bytes(), "the package's front-end.bin is not this cook's"
print(f"PASS front-end cook: twice identical, {len(cooked[0])} bytes, the package's own")

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


def lit_share(path, rect):
    """The share of the rect's middle row that is lit (the bar's fill)."""
    width, _, body = pixels(path)
    y = (rect[1] + rect[3]) // 2
    row = [body[(y * width + x) * 3:(y * width + x) * 3 + 3] for x in range(rect[0], rect[2])]
    return sum(sum(p) > 200 for p in row) / len(row)


realm = B / "realm.json"
realm.write_text('{"id": "front-end", "name": "Local Realm", "host": "127.0.0.1", "port": 1, '
                 '"discord_client_id": "0"}')
for size in ("1280x800", "1024x768"):
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
                          "loading-start", "loading-world", "message"}, shots.keys()

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

    start, rect, _ = shots["loading-start"]
    world = shots["loading-world"][0]
    share = lit_share(start, rect), lit_share(world, rect)
    assert 0.5 < share[0] < 0.8 and share[1] > 0.95, (size, rect, share)

    path, rect, _ = shots["message"]
    assert len(set(region(path, rect))) > 10, (size, rect)
    print(f"PASS front-end captures {size}: intro box {boxes and shots['login'][2][0][1]}, "
          f"realm name {inside} px in the list, 1-3 characters in the hall, loading {share[0]:.2f} -> {share[1]:.2f}")
print("PASS KO front end graphical")
