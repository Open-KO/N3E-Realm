"""PQ-316: the screen bloom and tone map (postprocess.bin, N3PF), live.

The chain is the 2233 client's CN3PostProcess (a 2233/2145 addition; KO 1298
has none): the main render (00537030) draws the world into an 8-bit scene
target and runs 00476b40 before the HUD; P0 keeps the 2x2 average whose
luminance reaches the threshold (00475000, 00474ef0); P1 and P2 x5 reduce the
scene's log-average, maximum and minimum luminance to one texel, which is read
back (00475350); P3 downscales the bright pass 4x4 (00475860); P4 and P5 blur
it across and down with nine Gaussian taps whose weights are scaled by the
bloom scale (00475ca0, 004759f0); P6 adapts the measured values at the
package's rate per second and composites scene plus bloom through the
extended Reinhard tone map, lift and saturation (00476690, 00474b50; the pass
bodies from the 2145 pp.fx, local-asset). Evidence:
docs/implementation/evidence/pq-316-hdr-bloom-post-process-2233.md.

The package is the PQ-272 fixture (tests/npc_scale_live.py) with an original
synthetic `postprocess` record. Both readers must accept it and refuse
malformed files. With N3E_GRAPHICAL=1 the real test client runs offline at
256x192 and:

- with Option.ini [Addition2233] HDR=1 over a known picture: one-pixel
  stripes (the measured average is the geometric mean of each 2x2 block,
  about 1/255, not the arithmetic 0.5), then a uniform grey (the measured
  values settle on it and the adapted ones follow at the package rate, frame
  by frame, after a first-frame snap), then a dark picture with an off-centre
  white, a light grey and a red square: that frame's read-back (read
  synchronously) must equal a CPU reference of the whole reduction (P1's 2x2
  geometric means, then P2's five 3x3 mean, maximum and minimum passes) of its
  own scene, every stage (bright pass, downscale, blur across, blur down,
  composite) must equal a CPU reference computed from the stage before it, the
  two squares above the threshold must bloom and the red one below it must
  not; then black until the adapted average and maximum reach 0, where the
  composite must use the D-185 floor (1/255) and draw black, equal to its
  reference;
- over the package's own scene at a fixed animation time, on and with the
  option at its default (off): the default draws the plain scene (equal to the
  on run's scene stage), the on run's read-back and stages equal their references, and the
  HUD drawn after the composite (the FPS panel) keeps its own colour;
- with HDR=1 on the same fixture without the record: no post-process.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tests") not in sys.path:
    sys.path.append(str(ROOT / "tests"))
from isolation import once_per_run  # noqa: E402
import npc_looks_live  # noqa: E402

OUT = ROOT / "build/pq316"
SIZE = (256, 192)
# Original synthetic settings: none is KO's; each stage changes the picture.
SETTINGS = dict(threshold=0.4, bloom=1.25, exposure=0.5, saturation=1.3, lift=0.3, adapt_rate=0.3, blur_variance=1.5)
LUM = (0.299, 0.587, 0.114)
# The picture's phases: stripes from frame 0, grey from 30, squares from 230,
# black from 300 (long enough for the adapted average and maximum to reach 0).
GREY = 191
# The white square is off the centre, so a reduction that kept only its centre
# texel would read the background there, not the white.
WHITE_BOX, LIGHT_BOX, RED_BOX = (152, 40, 32, 32), (200, 136, 24, 24), (24, 24, 32, 32)
LIGHT, RED, BACKGROUND = (150, 150, 150), (220, 40, 40), (10, 10, 10)
PATTERN = "|".join([
    "0@stripes",
    f"30@{GREY},{GREY},{GREY}",
    "230@%d,%d,%d;%s=255,255,255;%s=%d,%d,%d;%s=%d,%d,%d" % (
        *BACKGROUND, ",".join(map(str, WHITE_BOX)), ",".join(map(str, LIGHT_BOX)), *LIGHT,
        ",".join(map(str, RED_BOX)), *RED),
    "300@0,0,0",
])
PATTERN_STAGES, BLACK_STAGES, PATTERN_FRAMES = 260, 560, 590
FPS_PANEL = (SIZE[0] - 126, 8, SIZE[0] - 8, 36)  # draw_fps: 118 x 28 from the top-right
FPS_COLOUR = (5, 6, 8)  # glClearColor(.02, .025, .03)


@once_per_run
def prepare():
    """Cook the PQ-272 package with the synthetic postprocess record; returns it."""
    from npc_scale_live import prepare as base
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    import main

    source = base().parent / "source"
    root, out = OUT / "source", OUT / "package"
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(source, root)
    m = json.loads((root / "package.json").read_text())
    assert m["engine_version"] >= 33 and "presentation" in m and "postprocess" not in m
    m["postprocess"] = SETTINGS
    (root / "package.json").write_text(json.dumps(m))
    main.cook(root, out)
    return out.resolve()


def repack(package, out, name, data):
    """A copy of `package` whose `name` is `data`, rehashed into release.bin."""
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(package, out)
    (out / name).write_bytes(data)
    m = json.loads((out / "recipe.json").read_text())["manifest"]
    u = lambda *xs: b"".join(struct.pack("<I", x) for x in xs)  # noqa: E731
    string = lambda s: u(len(s)) + s.encode()  # noqa: E731
    names = sorted(p.name for p in out.iterdir() if p.name not in ("release.bin", "release.sha256"))
    index = b"N3R1" + u(1, m["engine_version"], m["protocol_version"]) + string(m["game_id"]) \
        + string(m["package_version"]) + u(len(names))
    for n in names:
        d = (out / n).read_bytes()
        index += string(n) + u(len(d)) + hashlib.sha256(d).digest()
    (out / "release.bin").write_bytes(index)


def readers(package, good):
    for command in (["build/client/n3e-asset-check", str(package)], ["target/debug/n3e-server", "--check-content"]):
        p = subprocess.run(command, cwd=ROOT, env={**os.environ, "N3E_PACKAGE": str(package)},
                           capture_output=True, text=True)
        assert (p.returncode == 0) == good, (command, package, p.stdout[-600:], p.stderr[-600:])


def check_readers(package):
    readers(package, True)
    values = [SETTINGS[k] for k in ("threshold", "bloom", "exposure", "saturation", "lift", "adapt_rate",
                                    "blur_variance")]
    bad = OUT / "hostile"
    cases = {
        "magic": b"N3PG" + struct.pack("<7f", *values),
        "trailing": b"N3PF" + struct.pack("<7f", *values) + b"\0",
        "variance zero": b"N3PF" + struct.pack("<7f", *values[:6], 0.0),
        "bloom high": b"N3PF" + struct.pack("<7f", values[0], 4.5, *values[2:]),
    }
    for data in cases.values():
        repack(package, bad, "postprocess.bin", data)
        readers(bad, False)
    shutil.rmtree(bad)
    return len(cases)


# ---- the CPU reference of each stage (client/render/postprocess.h) ----

class Image:
    def __init__(self, path):
        self.width, self.height, data = npc_looks_live.read_ppm(Path(path))
        self.rgb = [tuple(data[i:i + 3]) for i in range(0, len(data), 3)]

    def at(self, x, y):
        """Clamped to the edge, as every target samples."""
        x, y = min(max(x, 0), self.width - 1), min(max(y, 0), self.height - 1)
        return self.rgb[y * self.width + x]


def luminance(c):
    return sum(w * v for w, v in zip(LUM, c))


def to8(c):
    return tuple(min(255, max(0, int(math.floor(v * 255 + .5)))) for v in c)


def bright_at(scene, x, y, threshold):
    taps = [scene.at(2 * x + dx, 2 * y + dy) for dy in (0, 1) for dx in (0, 1)]
    c = [sum(t[i] for t in taps) / 4 / 255 for i in range(3)]
    l = luminance(c)
    return (to8(c) if l >= threshold else (0, 0, 0)), abs(l - threshold) < 1.5 / 255


def down_at(bright, x, y):
    taps = [bright.at(4 * x + dx, 4 * y + dy) for dy in range(4) for dx in range(4)]
    return to8([sum(t[i] for t in taps) / 16 / 255 for i in range(3)]), False


def weights(variance, bloom):
    w = [math.exp(-(i - 4) ** 2 / (2 * variance)) for i in range(9)]
    return [x / sum(w) * bloom for x in w]


def blur_at(source, x, y, across, w):
    taps = [source.at(x + k - 4, y) if across else source.at(x, y + k - 4) for k in range(9)]
    return to8([sum(wk * t[i] for wk, t in zip(w, taps)) / 255 for i in range(3)]), False


def bilinear(image, u, v):
    x, y = u * image.width - .5, v * image.height - .5
    x0, y0 = math.floor(x), math.floor(y)
    fx, fy = x - x0, y - y0
    c = [0.0, 0.0, 0.0]
    for dy, wy in ((0, 1 - fy), (1, fy)):
        for dx, wx in ((0, 1 - fx), (1, fx)):
            t = image.at(x0 + dx, y0 + dy)
            for i in range(3):
                c[i] += wx * wy * t[i] / 255
    return c


def tone_map(c, average, maximum, s):
    white = maximum * s["bloom"] + maximum
    l = luminance(c) / average
    lm = l * s["exposure"]
    k = lm * (lm / (white * white) + 1) / (s["exposure"] * l + 1) + s["lift"]
    t = [v * k for v in c]
    g = luminance(t)
    return [s["saturation"] * (v - g) + g for v in t]


def final_at(scene, bloom, x, y, average, maximum, s, with_bloom=True):
    b = bilinear(bloom, (x + .5) / scene.width, (y + .5) / scene.height) if with_bloom else [0, 0, 0]
    c = [scene.at(x, y)[i] / 255 + b[i] for i in range(3)]
    return to8(tone_map(c, average, maximum, s)), False


def check_stage(image, at, tolerance, stride=1):
    """(largest difference, pixels over the tolerance, pixels compared) over
    every `stride`-th pixel in each direction."""
    worst, over, compared = 0, 0, 0
    for y in range(0, image.height, stride):
        for x in range(0, image.width, stride):
            want, borderline = at(x, y)
            if borderline:
                continue
            compared += 1
            d = max(abs(a - b) for a, b in zip(image.at(x, y), want))
            worst = max(worst, d)
            over += d > tolerance
    return worst, over, compared


def compare(name, image, reference, tolerance, skip=lambda x, y: False):
    """Two whole images: (largest difference, pixels over the tolerance, pixels compared)."""
    assert len(image.rgb) == len(reference), (name, len(image.rgb), len(reference))
    worst, over, compared = 0, 0, 0
    for i, (got, (want, borderline)) in enumerate(zip(image.rgb, reference)):
        if borderline or skip(i % image.width, i // image.width):
            continue
        compared += 1
        d = max(abs(a - b) for a, b in zip(got, want))
        worst = max(worst, d)
        over += d > tolerance
    return worst, over, compared


def stages(log, frame):
    """The stage images the client wrote for `frame`."""
    found = dict(re.findall(r"^POSTPROCESS_STAGE frame=%d name=(\w+) width=\d+ height=\d+ path=(.+)$" % frame, log, re.M))
    assert set(found) == {"scene", "bright", "down", "blur", "bloom", "final"}, (frame, found, log[-1500:])
    return {k: Image(ROOT / v) for k, v in found.items()}


class Grid:
    """An 8-bit image held in memory, sampled like Image."""
    def __init__(self, width, height, rgb):
        self.width, self.height, self.rgb = width, height, rgb

    def at(self, x, y):
        x, y = min(max(x, 0), self.width - 1), min(max(y, 0), self.height - 1)
        return self.rgb[y * self.width + x]


def reduction_reference(scene):
    """The read-back the scene gives (00475350): P1 at half size, each texel
    the geometric mean (x), maximum (y) and minimum (z) of a 2x2 block's
    luminance, in 8 bits; then P2 into 81, 27, 9, 3 and 1 texels, each the
    mean, maximum and minimum of nine bilinear taps at -1/0/+1 source texel,
    in 8 bits. Returns the 1x1 (x, y, z) in levels."""
    half = []
    for y in range(scene.height // 2):
        for x in range(scene.width // 2):
            ls = [luminance([v / 255 for v in scene.at(2 * x + dx, 2 * y + dy)]) for dy in (0, 1) for dx in (0, 1)]
            mean = 2 ** (sum(math.log2(l + 1e-5) * .173287 for l in ls) * 1.4427)
            half.append(to8([mean, max(ls), min(10, min(ls))]))
    source = Grid(scene.width // 2, scene.height // 2, half)
    for n in (81, 27, 9, 3, 1):
        out = []
        for j in range(n):
            for i in range(n):
                u, v = (i + .5) / n, (j + .5) / n
                taps = [bilinear(source, u + dx / source.width, v + dy / source.height)
                        for dy in (-1, 0, 1) for dx in (-1, 0, 1)]
                out.append(to8([sum(t[0] for t in taps) * .111111, max(t[1] for t in taps), min(t[2] for t in taps)]))
        source = Grid(n, n, out)
    return source.rgb[0]


def check_reduction(scene, measured, label, tolerance=2):
    """The client's read-back of this frame (read synchronously on a stage
    frame) against the reference of its own scene."""
    want, got = reduction_reference(scene), [round(v * 255) for v in measured]
    assert all(abs(a - b) <= tolerance for a, b in zip(got, want)), (label, "reduction", got, want)
    return got, want


def frames(log):
    rows = re.findall(r"^POSTPROCESS frame=(\d+) dt=([0-9.e+-]+) read=(\w+) measured=([^ ]+) adapted=([^ ]+) "
                      r"used=([^ ]+)$", log, re.M)
    out = {}
    for f, dt, read, m, a, used in rows:
        out[int(f)] = dict(dt=float(dt), read=read, measured=[float(x) for x in m.split(",")],
                           adapted=[float(x) for x in a.split(",")], used=[float(x) for x in used.split(",")])
    return out


def check_chain(images, used, label, s=SETTINGS, stride=1):
    """Every stage against the reference from the stage before it (sampled
    every `stride` pixels); returns the largest differences."""
    w, report = weights(s["blur_variance"], s["bloom"]), {}
    sc, br, dn, bl, bm = (images[k] for k in ("scene", "bright", "down", "blur", "bloom"))
    checks = [
        ("bright", lambda x, y: bright_at(sc, x, y, s["threshold"]), 2),
        ("down", lambda x, y: down_at(br, x, y), 1),
        ("blur", lambda x, y: blur_at(dn, x, y, True, w), 1),
        ("bloom", lambda x, y: blur_at(bl, x, y, False, w), 1),
        ("final", lambda x, y: final_at(sc, bm, x, y, used[0], used[1], s), 3),
    ]
    for name, at, tolerance in checks:
        worst, over, compared = check_stage(images[name], at, tolerance, stride if name != "down" else 1)
        assert compared > 0 and over == 0, (label, name, worst, over, compared)
        report[name] = worst
    return report


def client(package, capture, config, extra_env=None, args=()):
    env = {**os.environ, "XDG_CONFIG_HOME": str(config), **(extra_env or {})}
    p = subprocess.run(["build/client/n3e-test-client", str(package), "--smoke", "--fixed-window",
                        "%dx%d" % SIZE, "--capture", str(capture), *args], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=120)
    log = p.stdout + p.stderr
    capture.with_suffix(".log").write_text(log)
    assert p.returncode == 0, (capture, p.returncode, log[-2000:])
    return log


def option(directory, hdr):
    (directory / "n3e").mkdir(parents=True, exist_ok=True)
    (directory / "n3e" / "Option.ini").write_text("[Addition2233]\nHDR=%d\n" % hdr if hdr is not None else "")
    return directory


def graphical(package):
    from npc_scale_live import prepare as base
    out = OUT / "live"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    with tempfile.TemporaryDirectory(dir=OUT) as tmp:
        tmp = Path(tmp)
        on, default = option(tmp / "on", 1), option(tmp / "default", None)

        # 1. The known picture with the post-process on.
        log = client(package, out / "pattern.ppm", on, {
            "N3E_TEST_POSTPROCESS": "1", "N3E_TEST_POSTPROCESS_PATTERN": PATTERN,
            "N3E_TEST_POSTPROCESS_STAGES": f"{PATTERN_STAGES},{BLACK_STAGES}",
            "N3E_TEST_POSTPROCESS_FRAMES": str(PATTERN_FRAMES)})
        assert "HDR bloom: a 2233/2145 addition (N3PF), on" in log, log[:2000]
        f = frames(log)
        assert len(f) >= PATTERN_FRAMES - 5 and f[0]["read"] == "sync", (len(f), f.get(0))
        # Stripes: P1's geometric mean of each 2x2 block (two white, two
        # black texels) is about 0.003, so the average reads 0 or 1 of 255;
        # an arithmetic mean would read about 128. Maximum 1, minimum 0.
        m0 = f[0]["measured"]
        assert m0[0] * 255 <= 1.5 and m0[1] == 1 and m0[2] == 0, m0
        assert f[0]["adapted"] == m0, "the first frame snaps (+0x73)"
        # Grey: the measured values settle on 191 / 255; the adapted ones step
        # by rate x dt toward them each frame (00476690), never past them.
        settled = [n for n in range(30, PATTERN_STAGES) if n in f and
                   all(abs(v * 255 - GREY) <= 1 for v in f[n]["measured"])]
        assert settled and settled[0] <= 36, settled[:3]
        moved, worst = 0, 0.0
        for n in range(1, PATTERN_FRAMES):
            if n not in f or n - 1 not in f:
                continue
            step = SETTINGS["adapt_rate"] * f[n]["dt"]
            for i in range(3):
                a, m, prev = f[n]["adapted"][i], f[n]["measured"][i], f[n - 1]["adapted"][i]
                want = prev + (-step if m <= prev else step) if step <= abs(prev - m) else m
                worst = max(worst, abs(a - want))
                moved += abs(a - prev) > 1e-6
        assert worst < 2e-5, worst
        grey = GREY / 255
        gap = grey - m0[0]
        reached = next(n for n in range(30, PATTERN_STAGES) if n in f and abs(f[n]["adapted"][0] - grey) < 1e-5)
        took = sum(f[n]["dt"] for n in range(settled[0] + 1, reached + 1) if n in f)
        assert abs(took - gap / SETTINGS["adapt_rate"]) < 0.1, (took, gap / SETTINGS["adapt_rate"])
        reads = {f[n]["read"] for n in f}
        assert "async" in reads and reads <= {"sync", "async", "pending"}, reads
        print(f"PASS luminance reduction and adaptation: stripes read {m0[0] * 255:.0f}/255 (log average, not 128), "
              f"grey reads {GREY}/255 by frame {settled[0]}; adapted values follow 00476690's step at "
              f"{SETTINGS['adapt_rate']}/s on every frame (worst {worst:.1e}), closing the {gap:.3f} gap in "
              f"{took:.2f} s; read-backs {sorted(reads)}", flush=True)
        images = stages(log, PATTERN_STAGES)
        used = f[PATTERN_STAGES]["used"]
        assert f[PATTERN_STAGES]["read"] == "sync", f[PATTERN_STAGES]
        # The reduction (P1, then P2 five times) of a picture that is not
        # uniform after P1: the maximum is the off-centre white square's, the
        # minimum the background's, the average the chain's means.
        reduced, expected = check_reduction(images["scene"], f[PATTERN_STAGES]["measured"], "pattern")
        assert reduced[1] == 255 and reduced[2] == 10 < reduced[0] < 128, reduced  # background (10, 10, 10)
        report = check_chain(images, used, "pattern")
        # Halo: just outside each square above the threshold the composite is
        # brighter than the same tone map without bloom; not beside the red one.
        def halo(box):
            x, y, w, h = box
            ring = [(px, py) for px in range(x - 3, x + w + 3) for py in range(y - 3, y + h + 3)
                    if not (x <= px < x + w and y <= py < y + h)]
            final = images["final"]
            return max(sum(final.at(px, py)) - sum(final_at(images["scene"], images["bloom"], px, py, used[0],
                                                            used[1], SETTINGS, with_bloom=False)[0])
                       for px, py in ring)
        halos = {name: halo(box) for name, box in (("white", WHITE_BOX), ("light", LIGHT_BOX), ("red", RED_BOX))}
        assert halos["white"] >= 60 and halos["light"] >= 30 and halos["red"] <= 3, halos
        bright = images["bright"]
        x, y, w, h = RED_BOX
        assert all(bright.at(px // 2, py // 2) == (0, 0, 0) for px in range(x + 2, x + w - 2)
                   for py in range(y + 2, y + h - 2)), "the red square is below the threshold"
        print(f"PASS every stage of the picture equals its reference (read-back {reduced} levels against the "
              f"reduction reference {expected}; largest differences {report}); squares above the threshold bloom "
              f"(halo {halos['white']} and {halos['light']} levels over the composite without bloom), the red one "
              f"below it does not ({halos['red']})", flush=True)
        # Black: the read-back is 0, the adapted average and maximum reach 0,
        # and the composite divides by the D-185 floor, 1/255, not by 0 (2233
        # would divide by zero); the drawn frame is black and equals its reference.
        zero = next((n for n in range(300, BLACK_STAGES) if n in f and f[n]["adapted"][:2] == [0, 0]), None)
        assert zero is not None, [f[n]["adapted"] for n in (300, BLACK_STAGES - 1) if n in f]
        black = f[BLACK_STAGES]
        assert black["measured"] == [0, 0, 0] and black["adapted"] == [0, 0, 0], black
        assert all(abs(u - 1 / 255) < 1e-6 for u in black["used"]), ("the floor", black["used"])
        dark = stages(log, BLACK_STAGES)
        check_reduction(dark["scene"], black["measured"], "black", tolerance=0)
        black_report = check_chain(dark, black["used"], "black")
        assert set(dark["final"].rgb) == {(0, 0, 0)}, set(dark["final"].rgb)
        print(f"PASS a black frame: the read-back is 0, the adapted average and maximum reach 0 by frame {zero}, the "
              f"composite divides by the 1/255 floor (used {black['used']}) and draws black, equal to its reference "
              f"({black_report})", flush=True)

        # 2. The package's own scene, on and at the default.
        fixed = ["--time", "0.5"]
        log_on = client(package, out / "scene-on.ppm", on, {"N3E_TEST_POSTPROCESS": "1",
                                                             "N3E_TEST_POSTPROCESS_STAGES": "40"}, fixed)
        log_off = client(package, out / "scene-off.ppm", default, {"N3E_TEST_POSTPROCESS": "1"}, fixed)
        assert "HDR bloom: a 2233/2145 addition (N3PF), off; Option.ini [Addition2233] HDR=1 turns it on" in log_off
        assert "POSTPROCESS " not in log_off, "no post-process at the default"
        scene_on, f_on = stages(log_on, 40), frames(log_on)
        scene_reduced, _ = check_reduction(scene_on["scene"], f_on[40]["measured"], "scene")
        scene_report = check_chain(scene_on, f_on[40]["used"], "scene")
        panel = lambda x, y: FPS_PANEL[0] <= x < FPS_PANEL[2] and FPS_PANEL[1] <= y < FPS_PANEL[3]  # noqa: E731
        off_capture, on_capture = Image(out / "scene-off.ppm"), Image(out / "scene-on.ppm")
        identical = [(c, False) for c in scene_on["scene"].rgb]
        worst_off, over_off, _ = compare("off", off_capture, identical, 1, panel)
        assert over_off == 0, ("the default draws the plain scene", worst_off, over_off)
        worst_final, over_final, _ = compare("on", on_capture, [(c, False) for c in scene_on["final"].rgb], 0, panel)
        assert over_final == 0, ("the window shows the composite", worst_final, over_final)
        changed = sum(1 for a, b in zip(on_capture.rgb, off_capture.rgb) if max(abs(p - q) for p, q in zip(a, b)) > 8)
        assert changed > len(on_capture.rgb) // 4, changed
        x0, y0, x1, y1 = FPS_PANEL
        corners = {on_capture.at(x, y) for x, y in ((x0 + 1, y0 + 1), (x1 - 2, y0 + 1), (x0 + 1, y1 - 2))}
        assert corners == {FPS_COLOUR}, corners
        print(f"PASS the package scene: the default (off) draws the plain scene (the on run's scene stage, within "
              f"{worst_off} level), the on run's read-back {scene_reduced} and stages equal their references "
              f"({scene_report}), {changed} of "
              f"{len(on_capture.rgb)} pixels differ, and the HUD drawn after it keeps its colour {FPS_COLOUR}",
              flush=True)

        # 3. The same fixture without the record: nothing to draw.
        plain_log = client(base(), out / "no-record.ppm", on, {"N3E_TEST_POSTPROCESS": "1"}, fixed)
        assert "HDR bloom" not in plain_log and "POSTPROCESS" not in plain_log, plain_log[-1500:]
    captures = sorted(str(p.relative_to(ROOT)) for p in out.glob("*.ppm"))
    print("PASS graphical client draws the HDR bloom and tone map on and off: the picture's and the scene's every "
          "stage and read-back, the adaptation, the black frame's floor and the HUD after it; " + ", ".join(captures), flush=True)


if __name__ == "__main__":
    os.chdir(ROOT)
    package = prepare()
    assert (package / "postprocess.bin").read_bytes()[:4] == b"N3PF"
    refused = check_readers(package)
    print(f"PASS N3PF package: both readers accept it and refuse {refused} malformed postprocess files", flush=True)
    if os.environ.get("N3E_GRAPHICAL") == "1":
        graphical(package)
