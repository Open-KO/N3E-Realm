#!/usr/bin/env python3
"""Ashgrave: an original occult-noir exploration package built without KO assets.

Exploration spike (2026-09-25). Everything here is generated procedurally from
the standard library: pixel-art textures, a small night-time borough (chapel,
terraces, gas lamps, graveyard) as an N3W1 world with matching collision, a
trench-coated investigator and a horned imp as skinned glTF with eleven clips,
and an N3H1 HUD. The theme is loosely inspired by occult-noir comics; it uses no
licensed names, likenesses or trademarks.

    python3 tools/assetc/ashgrave.py            # writes build/ashgrave-src and
                                                # cooks build/packages/ashgrave
"""
import json
import math
import random
import re
import shutil
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gltf  # noqa: E402
import main  # noqa: E402
from common import f, string, u  # noqa: E402

SRC = Path("build/ashgrave-src")
OUT = Path("build/packages/ashgrave")
GAME = "ashgrave"


# ---------------------------------------------------------------- images

def png_rgb(width, height, rgb):
    """RGB8, non-interlaced, IHDR/IDAT/IEND only: the subset gltf.cook accepts."""
    rows = b"".join(b"\0" + bytes(rgb[y * width * 3:(y + 1) * width * 3]) for y in range(height))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


class Canvas:
    def __init__(self, w, h, fill=(0, 0, 0, 255)):
        self.w, self.h = w, h
        self.px = [list(fill) for _ in range(w * h)]

    def set(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[y * self.w + x] = list(c) + ([255] if len(c) == 3 else [])

    def get(self, x, y):
        return self.px[(y % self.h) * self.w + (x % self.w)]

    def rect(self, x0, y0, x1, y1, c):
        for y in range(y0, y1):
            for x in range(x0, x1):
                self.set(x, y, c)


def shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c[:3])


def jitter(rng, c, amount):
    k = 1 + rng.uniform(-amount, amount)
    return shade(c, k)


# ---------------------------------------------------------------- world tiles

TILE = 56      # inner texels per atlas cell
CELL = 64
PAD = 4
ATLAS = 512


def tile(name, rng):
    t = Canvas(TILE, TILE)
    if name == "clear":
        t.px = [[0, 0, 0, 0] for _ in range(TILE * TILE)]
    elif name == "cobble":
        t.rect(0, 0, TILE, TILE, (28, 28, 32))
        for row in range(7):
            y0 = row * 8
            off = 4 if row % 2 else 0
            for col in range(8):
                x0 = col * 7 + off
                base = jitter(rng, (60, 60, 68), .3)
                for y in range(y0 + 1, y0 + 7):
                    for x in range(x0 + 1, x0 + 7):
                        edge = y in (y0 + 1, y0 + 6) or x % TILE in ((x0 + 1) % TILE, (x0 + 6) % TILE)
                        c = shade(base, .8 if edge else 1)
                        if y == y0 + 2 and rng.random() < .35:
                            c = shade(base, 1.35)   # wet highlight
                        t.set(x % TILE, y, c)
    elif name == "brick":
        t.rect(0, 0, TILE, TILE, (40, 30, 28))
        for row in range(TILE // 7):
            off = 7 if row % 2 else 0
            for col in range(-1, TILE // 14 + 1):
                base = jitter(rng, (98, 44, 36), .22)
                if rng.random() < .15:
                    base = shade(base, .6)   # soot
                for y in range(row * 7 + 1, row * 7 + 7):
                    for x in range(col * 14 + off + 1, col * 14 + off + 14):
                        t.set(x % TILE, y, jitter(rng, base, .06))
    elif name == "slate":
        t.rect(0, 0, TILE, TILE, (22, 24, 30))
        for row in range(TILE // 8):
            off = 5 if row % 2 else 0
            for col in range(-1, TILE // 10 + 1):
                base = jitter(rng, (54, 58, 70), .2)
                for y in range(row * 8, row * 8 + 7):
                    for x in range(col * 10 + off, col * 10 + off + 9):
                        t.set(x % TILE, y, shade(base, 1 - .03 * (y - row * 8)))
    elif name == "ashlar":
        t.rect(0, 0, TILE, TILE, (46, 46, 48))
        for row in range(4):
            off = 9 if row % 2 else 0
            for col in range(-1, 3):
                base = jitter(rng, (104, 102, 96), .12)
                for y in range(row * 14 + 1, row * 14 + 14):
                    for x in range(col * 28 + off + 1, col * 28 + off + 28):
                        c = jitter(rng, base, .05)
                        if rng.random() < .02:
                            c = (58, 72, 50)   # lichen
                        t.set(x % TILE, y, c)
    elif name == "grass":
        for y in range(TILE):
            for x in range(TILE):
                c = jitter(rng, (42, 50, 30), .3)
                if rng.random() < .08:
                    c = (70, 62, 40)
                t.set(x, y, c)
    elif name == "mud":
        for y in range(TILE):
            for x in range(TILE):
                t.set(x, y, jitter(rng, (52, 42, 34), .25))
    elif name in ("window_lit", "window_dark", "stained"):
        t.rect(0, 0, TILE, TILE, (26, 20, 18))
        for py in range(2):
            for px in range(2):
                for y in range(4 + py * 26, 4 + py * 26 + 22):
                    for x in range(4 + px * 25, 4 + px * 25 + 22):
                        if name == "window_lit":
                            c = jitter(rng, (230, 170, 80), .12)
                        elif name == "window_dark":
                            c = jitter(rng, (18, 24, 36), .3)
                        else:
                            c = [(150, 30, 40), (40, 60, 150), (200, 150, 50), (40, 110, 60)][(x // 6 + y // 7) % 4]
                        t.set(x, y, c)
    elif name == "door":
        for y in range(TILE):
            for x in range(TILE):
                plank = x // 9
                c = jitter(rng, (58 + plank * 3, 34, 24), .15)
                if x % 9 == 0:
                    c = (20, 12, 10)
                t.set(x, y, c)
        t.rect(40, 26, 44, 30, (160, 140, 60))   # brass handle
    elif name == "iron":
        t.rect(0, 0, TILE, TILE, (18, 18, 22))
        for y in range(TILE):
            t.set(y % TILE, y, (40, 40, 48))
    elif name == "railing":
        t.px = [[0, 0, 0, 0] for _ in range(TILE * TILE)]
        for x in range(TILE):
            for y in range(TILE):
                bar = x % 14 in (6, 7)
                rail = y in (6, 7, 48, 49)
                if bar or rail:
                    t.set(x, y, (24, 24, 30))
            if x % 14 in (5, 6, 7, 8):
                for y in range(0, 4):
                    t.set(x, y, (30, 30, 36))   # spear tips
    elif name == "headstone":
        for y in range(TILE):
            for x in range(TILE):
                c = jitter(rng, (92, 94, 92), .12)
                if rng.random() < .05:
                    c = (60, 74, 54)
                t.set(x, y, c)
        for y in (18, 24, 30):
            t.rect(14, y, 42, y + 2, (40, 42, 42))   # carved lines
        t.rect(26, 6, 30, 16, (40, 42, 42))
        t.rect(22, 9, 34, 12, (40, 42, 42))       # cross
    elif name == "lamp":
        t.rect(0, 0, TILE, TILE, (255, 200, 110))
        for y in range(TILE):
            for x in range(TILE):
                d = math.hypot(x - 28, y - 28) / 40
                t.set(x, y, shade((255, 210, 120), 1.1 - d * .5))
    elif name == "glow":
        t.rect(0, 0, TILE, TILE, (70, 44, 14))
    elif name == "glow_violet":
        t.rect(0, 0, TILE, TILE, (40, 14, 60))
    elif name == "plaster":
        for y in range(TILE):
            for x in range(TILE):
                c = jitter(rng, (120, 112, 96), .08)
                if y > 40:
                    c = shade(c, .7 + (y - 40) * .01)   # rising damp
                t.set(x, y, c)
    elif name == "wood":
        for y in range(TILE):
            for x in range(TILE):
                c = jitter(rng, (70, 50, 34), .1)
                if y % 11 == 0:
                    c = (30, 20, 14)
                t.set(x, y, c)
    elif name == "flag":
        t.rect(0, 0, TILE, TILE, (36, 36, 40))
        for row in range(2):
            for col in range(2):
                base = jitter(rng, (84, 82, 80), .1)
                t.rect(col * 28 + 1, row * 28 + 1, col * 28 + 27, row * 28 + 27, base)
    elif name == "bark":
        for y in range(TILE):
            for x in range(TILE):
                c = jitter(rng, (38, 32, 28), .2)
                if x % 7 == 0:
                    c = (20, 16, 14)
                t.set(x, y, c)
    elif name == "sign":
        t.rect(0, 0, TILE, TILE, (30, 18, 14))
        t.rect(4, 4, 52, 52, (90, 20, 24))
        for i in range(24):   # a crude hanged-man silhouette in gold
            t.set(28, 12 + i, (200, 160, 60))
        t.rect(22, 20, 35, 22, (200, 160, 60))
        t.rect(25, 36, 27, 46, (200, 160, 60))
        t.rect(30, 36, 32, 46, (200, 160, 60))
    else:
        raise ValueError(name)
    return t


TILES = ["clear", "cobble", "brick", "slate", "ashlar", "grass", "mud", "window_lit",
         "window_dark", "stained", "door", "iron", "railing", "headstone", "lamp", "glow",
         "glow_violet", "plaster", "wood", "flag", "bark", "sign"]
SLOT = {name: i for i, name in enumerate(TILES)}


def atlas():
    rng = random.Random(7)
    canvas = Canvas(ATLAS, ATLAS, (0, 0, 0, 0))
    per_row = ATLAS // CELL
    for i, name in enumerate(TILES):
        t = tile(name, rng)
        cx, cy = (i % per_row) * CELL, (i // per_row) * CELL
        for y in range(CELL):
            for x in range(CELL):
                # The pad replicates the wrapped tile so in-cell repeats stay seamless.
                canvas.set(cx + x, cy + y, t.get(x - PAD, y - PAD))
    return bytes(v for p in canvas.px for v in p)


# ---------------------------------------------------------------- geometry

def sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def norm(v):
    length = math.sqrt(dot(v, v)) or 1
    return [x / length for x in v]


class World:
    def __init__(self):
        self.vertices = []
        self.indices = []
        self.collision = []

    def quad(self, corners, normal, slot, uvs, slot2=0, collide=False):
        """Front faces are counter-clockwise seen from the normal side (GL_CCW)."""
        a, b, c, d = corners
        if dot(cross(sub(b, a), sub(c, a)), normal) < 0:
            corners = [a, d, c, b]
            uvs = [uvs[0], uvs[3], uvs[2], uvs[1]]
        start = len(self.vertices)
        n = norm(normal)
        for p, uv in zip(corners, uvs):
            self.vertices.append([p[0], p[1], p[2], n[0], n[1], n[2], uv[0], uv[1],
                                  uv[0], uv[1], float(slot), float(slot2)])
        self.indices += [start, start + 1, start + 2, start, start + 2, start + 3]
        if collide:
            a, b, c, d = corners
            self.collision += [a, b, c, a, c, d]

    def box(self, x0, y0, z0, x1, y1, z1, slot, top=None, scale=2.0, collide=True, slot2=0,
            faces="nsewtb", top_scale=None):
        """Axis-aligned box. UVs tile every `scale` metres of the face."""
        top = slot if top is None else top
        ts = top_scale or scale
        P = [[x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1],
             [x0, y1, z0], [x1, y1, z0], [x1, y1, z1], [x0, y1, z1]]
        w, h, d = x1 - x0, y1 - y0, z1 - z0

        def uv(a, b):
            return [[0, b / scale], [a / scale, b / scale], [a / scale, 0], [0, 0]]
        if "n" in faces:
            self.quad([P[1], P[0], P[4], P[5]], [0, 0, -1], slot, uv(w, h), slot2, collide)
        if "s" in faces:
            self.quad([P[3], P[2], P[6], P[7]], [0, 0, 1], slot, uv(w, h), slot2, collide)
        if "w" in faces:
            self.quad([P[0], P[3], P[7], P[4]], [-1, 0, 0], slot, uv(d, h), slot2, collide)
        if "e" in faces:
            self.quad([P[2], P[1], P[5], P[6]], [1, 0, 0], slot, uv(d, h), slot2, collide)
        if "t" in faces:
            self.quad([P[4], P[7], P[6], P[5]], [0, 1, 0], top,
                      [[0, 0], [0, d / ts], [w / ts, d / ts], [w / ts, 0]], 0, collide)
        if "b" in faces:
            self.quad([P[0], P[1], P[2], P[3]], [0, -1, 0], slot, uv(w, d), 0, False)

    def panel(self, center, size, facing, slot, slot2=0, lift=.02):
        """A flat decal (window, door, sign) standing just off a wall."""
        cx, cy, cz = center
        w, h = size
        nx, nz = facing
        tx, tz = -nz, nx
        o = [cx + nx * lift, cy, cz + nz * lift]
        corners = [[o[0] - tx * w / 2, cy - h / 2, o[2] - tz * w / 2], [o[0] + tx * w / 2, cy - h / 2, o[2] + tz * w / 2],
                   [o[0] + tx * w / 2, cy + h / 2, o[2] + tz * w / 2], [o[0] - tx * w / 2, cy + h / 2, o[2] - tz * w / 2]]
        self.quad(corners, [nx, 0, nz], slot, [[0, 1], [1, 1], [1, 0], [0, 0]], slot2)

    def gable(self, x0, z0, x1, z1, eave, ridge, axis, slot, wall):
        """Pitched roof over a rectangle; ridge along `axis` ('x' or 'z')."""
        if axis == "x":
            zm = (z0 + z1) / 2
            r0, r1 = [x0, ridge, zm], [x1, ridge, zm]
            slope = math.hypot(ridge - eave, zm - z0)
            self.quad([[x0, eave, z0], [x1, eave, z0], r1, r0], [0, zm - z0, -(ridge - eave)], slot,
                      [[0, slope / 2], [(x1 - x0) / 2, slope / 2], [(x1 - x0) / 2, 0], [0, 0]])
            self.quad([[x1, eave, z1], [x0, eave, z1], r0, r1], [0, zm - z0, (ridge - eave)], slot,
                      [[0, slope / 2], [(x1 - x0) / 2, slope / 2], [(x1 - x0) / 2, 0], [0, 0]])
            for x, s in ((x0, -1), (x1, 1)):
                self.tri([[x, eave, z0], [x, eave, z1], [x, ridge, zm]], [s, 0, 0], wall)
        else:
            xm = (x0 + x1) / 2
            r0, r1 = [xm, ridge, z0], [xm, ridge, z1]
            slope = math.hypot(ridge - eave, xm - x0)
            self.quad([[x0, eave, z1], [x0, eave, z0], r0, r1], [-(ridge - eave), xm - x0, 0], slot,
                      [[0, slope / 2], [(z1 - z0) / 2, slope / 2], [(z1 - z0) / 2, 0], [0, 0]])
            self.quad([[x1, eave, z0], [x1, eave, z1], r1, r0], [(ridge - eave), xm - x0, 0], slot,
                      [[0, slope / 2], [(z1 - z0) / 2, slope / 2], [(z1 - z0) / 2, 0], [0, 0]])
            for z, s in ((z0, -1), (z1, 1)):
                self.tri([[x0, eave, z], [x1, eave, z], [xm, ridge, z]], [0, 0, s], wall)

    def tri(self, pts, normal, slot):
        a, b, c = pts
        if dot(cross(sub(b, a), sub(c, a)), normal) < 0:
            pts = [a, c, b]
        start = len(self.vertices)
        n = norm(normal)
        for p in pts:
            u_ = (p[0] + p[2]) / 2
            self.vertices.append([p[0], p[1], p[2], n[0], n[1], n[2], u_, p[1] / 2, u_, p[1] / 2, float(slot), 0.0])
        self.indices += [start, start + 1, start + 2]

    def pyramid(self, x0, z0, x1, z1, base, apex, slot):
        cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
        top = [cx, apex, cz]
        for a, b, n in [([x0, base, z0], [x1, base, z0], [0, 1, -1]), ([x1, base, z0], [x1, base, z1], [1, 1, 0]),
                        ([x1, base, z1], [x0, base, z1], [0, 1, 1]), ([x0, base, z1], [x0, base, z0], [-1, 1, 0])]:
            self.tri([a, b, top], n, slot)


# ---------------------------------------------------------------- the borough

HALF = 48
SPACING = 2
SAMPLES = 2 * HALF // SPACING + 1   # 49


def height(x, z):
    # Flat streets; the graveyard (south-east) rises into a low barrow.
    h = 0.0
    d = math.hypot(x - 33, z - 32)
    if d < 14:
        h += 1.6 * (1 + math.cos(math.pi * d / 14)) / 2
    return round(h, 3)


def ground_slot(x, z):
    if 17 <= x and 17 <= z:
        return "grass"
    if -16 <= x <= 16 and -14 <= z <= 14:
        return "cobble"
    if -8 <= x <= 8 and -44 <= z < -14:
        return "flag"
    if abs(x) <= 16:
        return "cobble"
    return "mud" if (int(x // 6) + int(z // 6)) % 5 == 0 else "cobble"


def build_world():
    w = World()
    rng = random.Random(21)
    heights = [height(-HALF + x * SPACING, -HALF + z * SPACING) for z in range(SAMPLES) for x in range(SAMPLES)]
    # Terrain: the exact triangles collision cooks from the heightfield.
    for z in range(SAMPLES - 1):
        for x in range(SAMPLES - 1):
            X, Z = -HALF + x * SPACING, -HALF + z * SPACING
            a = [X, heights[z * SAMPLES + x], Z]
            b = [X, heights[(z + 1) * SAMPLES + x], Z + SPACING]
            c = [X + SPACING, heights[z * SAMPLES + x + 1], Z]
            d = [X + SPACING, heights[(z + 1) * SAMPLES + x + 1], Z + SPACING]
            slot = SLOT[ground_slot(X + 1, Z + 1)]
            start = len(w.vertices)
            for p in (a, b, c, d):
                n = [0, 1, 0]
                uvx, uvz = p[0] / 2, p[2] / 2
                w.vertices.append([p[0], p[1], p[2], *n, uvx, uvz, uvx, uvz, float(slot), 0.0])
            w.indices += [start, start + 1, start + 2, start + 2, start + 1, start + 3]

    def house(x0, z0, x1, z1, floors, facing, material, door_at):
        h = 3.2 * floors
        w.box(x0, 0, z0, x1, h, z1, SLOT[material], scale=2.4)
        axis = "z" if facing in ("e", "w") else "x"
        w.gable(x0 - .3, z0 - .3, x1 + .3, z1 + .3, h, h + 3.0, axis, SLOT["slate"], SLOT[material])
        # Chimney stacks.
        cx = x0 + 1 if axis == "z" else (x0 + x1) / 2 + 2
        cz = (z0 + z1) / 2 + 2 if axis == "z" else z0 + 1
        w.box(cx, h + 1.5, cz, cx + .9, h + 4.2, cz + .9, SLOT["brick"], scale=1.2, collide=False)
        nx, nz = {"e": (1, 0), "w": (-1, 0), "n": (0, -1), "s": (0, 1)}[facing]
        fx = x1 if facing == "e" else x0 if facing == "w" else None
        fz = z1 if facing == "s" else z0 if facing == "n" else None
        span = (z0, z1) if axis == "z" else (x0, x1)
        for floor in range(floors):
            y = 1.6 + floor * 3.2 + (.3 if floor else 0)
            for k, t in enumerate([.2, .5, .8]):
                along = span[0] + (span[1] - span[0]) * t
                if floor == 0 and k == door_at:
                    pos = [fx, 1.1, along] if axis == "z" else [along, 1.1, fz]
                    w.panel(pos, (1.2, 2.2), (nx, nz), SLOT["door"])
                    continue
                lit = rng.random() < .45
                pos = [fx, y, along] if axis == "z" else [along, y, fz]
                w.panel(pos, (1.3, 1.5), (nx, nz), SLOT["window_lit" if lit else "window_dark"],
                        SLOT["glow"] if lit else 0)

    # West terrace, facing east onto the square.
    z = -30
    for i, (depth_, floors, mat) in enumerate([(10, 3, "brick"), (8, 2, "plaster"), (9, 3, "brick"),
                                               (10, 2, "brick"), (8, 3, "plaster"), (9, 2, "brick")]):
        house(-30, z, -18, z + depth_, floors, "e", mat, i % 3)
        z += depth_
    # East terrace up to the pub, then the graveyard lane.
    z = -30
    for i, (depth_, floors, mat) in enumerate([(9, 2, "brick"), (10, 3, "plaster"), (9, 3, "brick")]):
        house(18, z, 30, z + depth_, floors, "w", mat, (i + 1) % 3)
        z += depth_
    # The Hanged Man public house.
    house(18, -2, 30, 12, 2, "w", "plaster", 1)
    w.box(17.2, 3.4, 4.6, 17.5, 3.5, 5.6, SLOT["iron"], collide=False)
    w.panel([17.3, 2.9, 5.1], (1.0, 1.1), (-1, 0), SLOT["sign"], SLOT["glow"], lift=.25)
    w.panel([17.3, 2.9, 5.1], (1.0, 1.1), (1, 0), SLOT["sign"], 0, lift=-.2)
    for bx, bz in [(16.5, 0.5), (16.4, 9.8), (15.6, 9.2)]:
        w.box(bx - .35, 0, bz - .35, bx + .35, .9, bz + .35, SLOT["wood"], scale=1)

    # St. Ashgrave's chapel: nave, tower and spire to the north.
    w.box(-7, 0, -42, 7, 8, -22, SLOT["ashlar"], scale=2.8)
    w.gable(-7.5, -42.5, 7.5, -21.5, 8, 13, "z", SLOT["slate"], SLOT["ashlar"])
    for zc in (-38, -33, -28):
        for side, sx in ((-1, -7), (1, 7)):
            w.panel([sx, 4.5, zc], (1.4, 3.6), (side, 0), SLOT["stained"], SLOT["glow_violet"])
    w.box(-3, 0, -22, 3, 18, -16, SLOT["ashlar"], scale=2.8)
    w.pyramid(-3.4, -22.4, 3.4, -15.6, 18, 27, SLOT["slate"])
    w.panel([0, 1.6, -16], (2.0, 3.2), (0, 1), SLOT["door"])
    w.panel([0, 12, -16], (1.6, 2.4), (0, 1), SLOT["stained"], SLOT["glow_violet"])
    w.panel([0, 15.5, -16], (1.2, 1.2), (0, 1), SLOT["window_dark"])

    # Memorial on the square: stepped plinth and obelisk.
    w.box(-2, 0, -2, 2, .4, 2, SLOT["ashlar"], scale=1.5)
    w.box(-1.4, .4, -1.4, 1.4, 1.2, 1.4, SLOT["ashlar"], scale=1.5)
    w.box(-.6, 1.2, -.6, .6, 5.2, .6, SLOT["ashlar"], scale=1.5)
    w.pyramid(-.6, -.6, .6, .6, 5.2, 6.2, SLOT["ashlar"])

    # Gas lamps around the square and along the lane.
    lamps = [(-14, -12), (14, -12), (-14, 12), (14, 12), (-14, 0), (14, 0), (0, 22), (0, 36), (-8, -12), (8, -12)]
    for lx, lz in lamps:
        w.box(lx - .09, 0, lz - .09, lx + .09, 3.3, lz + .09, SLOT["iron"], scale=1)
        w.box(lx - .28, 3.3, lz - .28, lx + .28, 3.9, lz + .28, SLOT["lamp"], SLOT["iron"], scale=.6,
              collide=False, slot2=SLOT["glow"])
        w.pyramid(lx - .34, lz - .34, lx + .34, lz + .34, 3.9, 4.25, SLOT["iron"])

    # The graveyard: railings with a gate gap, headstones, a mausoleum, dead trees.
    def railing(x0, z0, x1, z1):
        y = height((x0 + x1) / 2, (z0 + z1) / 2)
        length = math.hypot(x1 - x0, z1 - z0)
        n = norm([-(z1 - z0), 0, x1 - x0])
        for sgn in (1, -1):
            p = [[x0, y, z0], [x1, y, z1], [x1, y + 1.6, z1], [x0, y + 1.6, z0]]
            w.quad(p, [n[0] * sgn, 0, n[2] * sgn], SLOT["railing"],
                   [[0, 1], [length / 1.8, 1], [length / 1.8, 0], [0, 0]])
        # Thin collision wall along the railing.
        w.collision += [[x0, y - .5, z0], [x1, y - .5, z1], [x1, y + 2, z1],
                        [x0, y - .5, z0], [x1, y + 2, z1], [x0, y + 2, z0]]
    railing(17, 17, 17, 28)
    railing(17, 33, 17, 47)
    railing(17, 17, 47, 17)
    stones = []
    for gz in range(21, 46, 4):
        for gx in range(22, 46, 4):
            if rng.random() < .75 and not (28 <= gx <= 38 and 26 <= gz <= 38):
                stones.append((gx + rng.uniform(-.6, .6), gz + rng.uniform(-.6, .6)))
    for gx, gz in stones:
        y = height(gx, gz)
        tall = rng.uniform(.8, 1.4)
        w.box(gx - .4, y - .2, gz - .12, gx + .4, y + tall, gz + .12, SLOT["headstone"], scale=1, top=SLOT["headstone"])
    # Mausoleum on the barrow.
    y = height(33, 32)
    w.box(30, y - .5, 30, 36, y + 3.5, 35, SLOT["ashlar"], scale=2.4)
    w.gable(29.6, 29.6, 36.4, 35.4, y + 3.5, y + 5.3, "x", SLOT["slate"], SLOT["ashlar"])
    w.panel([33, y + 1.1, 30], (1.4, 2.2), (0, -1), SLOT["iron"])
    for tx, tz in [(24, 40), (42, 22), (44, 42)]:
        y = height(tx, tz)
        w.box(tx - .25, y - .2, tz - .25, tx + .25, y + 4.5, tz + .25, SLOT["bark"], scale=1)
        for k in range(4):
            a = k * math.pi / 2 + .5
            bx, bz = tx + math.cos(a) * 1.1, tz + math.sin(a) * 1.1
            w.box(min(tx, bx) - .08, y + 3 + k * .35, min(tz, bz) - .08, max(tx, bx) + .08, y + 3.18 + k * .35,
                  max(tz, bz) + .08, SLOT["bark"], scale=1, collide=False)

    # Boundary: soot-black brick walls with a dead end to the south.
    for x0, z0, x1, z1 in [(-48, -48, 48, -46), (-48, 46, 48, 48), (-48, -46, -46, 46), (46, -46, 48, 46)]:
        w.box(x0, 0, z0, x1, 4.5, z1, SLOT["brick"], scale=2.4)
    return w, heights


# ---------------------------------------------------------------- characters

def quat(axis, angle):
    s = math.sin(angle / 2)
    x, y, z = axis
    return [x * s, y * s, z * s, math.cos(angle / 2)]


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return [aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz]


def euler(x=0.0, y=0.0, z=0.0):
    q = qmul(quat([0, 1, 0], y), qmul(quat([1, 0, 0], x), quat([0, 0, 1], z)))
    length = math.sqrt(sum(v * v for v in q))
    return [v / length for v in q]


class Palette:
    """A 64x64 RGB texture of 8x8 swatches plus a few painted faces."""

    def __init__(self):
        self.c = Canvas(64, 64, (255, 0, 255))
        self.slots = {}

    def swatch(self, name, index, color, rng, noise=.08):
        x0, y0 = (index % 8) * 8, (index // 8) * 8
        for y in range(8):
            for x in range(8):
                self.c.set(x0 + x, y0 + y, jitter(rng, color, noise))
        self.slots[name] = (x0, y0)
        return self

    def uv(self, name, x0=1, y0=1, x1=7, y1=7):
        sx, sy = self.slots[name]
        return [(sx + x0) / 64, (sy + y0) / 64, (sx + x1) / 64, (sy + y1) / 64]

    def rgb(self):
        return [v for p in self.c.px for v in p[:3]]


class Rig:
    def __init__(self, joints):
        # joints: list of (name, parent index, translation)
        self.names = [j[0] for j in joints]
        self.parent = [j[1] for j in joints]
        self.t = [j[2] for j in joints]
        self.index = {n: i for i, n in enumerate(self.names)}
        self.world = []
        for i, p in enumerate(self.parent):
            base = self.world[p] if p >= 0 else [0, 0, 0]
            self.world.append([base[k] + self.t[i][k] for k in range(3)])
        self.pos, self.nrm, self.uvs, self.jnt, self.idx = [], [], [], [], []

    def box(self, joint, center, size, uv, face_uv=None):
        """A box rigidly skinned to `joint`; `face_uv` paints the -Z (front) face."""
        j = self.index[joint]
        cx, cy, cz = center
        sx, sy, sz = size[0] / 2, size[1] / 2, size[2] / 2
        c = [[cx + (sx if i & 1 else -sx), cy + (sy if i & 2 else -sy), cz + (sz if i & 4 else -sz)] for i in range(8)]
        faces = [([0, 4, 6, 2], [-1, 0, 0]), ([1, 3, 7, 5], [1, 0, 0]), ([0, 1, 5, 4], [0, -1, 0]),
                 ([2, 6, 7, 3], [0, 1, 0]), ([0, 2, 3, 1], [0, 0, -1]), ([4, 5, 7, 6], [0, 0, 1])]
        for face, normal in faces:
            u0, v0, u1, v1 = face_uv if (face_uv and normal == [0, 0, -1]) else uv
            corners = [c[i] for i in face]
            # Orient so the face is counter-clockwise from outside.
            if dot(cross(sub(corners[1], corners[0]), sub(corners[2], corners[0])), normal) < 0:
                corners = [corners[0], corners[3], corners[2], corners[1]]
            if normal == [0, 0, -1]:
                # Front face: image upright when seen from the front (from -Z, +X is on the left).
                order = sorted(range(4), key=lambda k: (-corners[k][1], -corners[k][0]))
                tl, tr = order[0], order[1]
                uvmap = {}
                for k in range(4):
                    top = corners[k][1] > cy
                    right = corners[k][0] < cx
                    uvmap[k] = [u1 if right else u0, v0 if top else v1]
                uvs = [uvmap[k] for k in range(4)]
                del tl, tr
            else:
                uvs = [[u0, v1], [u1, v1], [u1, v0], [u0, v0]]
            start = len(self.pos)
            for p, t in zip(corners, uvs):
                self.pos.append(p)
                self.nrm.append(normal)
                self.uvs.append(t)
                self.jnt.append(j)
            self.idx += [start, start + 1, start + 2, start, start + 2, start + 3]


def write_gltf(path, rig, texture, attachment, tracks, duration):
    """One mesh, one skin, one texture, one LINEAR animation (gltf.cook subset)."""
    blob = bytearray()
    views, accessors = [], []

    def add(data, kind, comp, count, fmt):
        while len(blob) % 4:
            blob.append(0)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)})
        blob.extend(data)
        accessors.append({"bufferView": len(views) - 1, "componentType": comp, "count": count, "type": kind})
        return len(accessors) - 1
    n = len(rig.pos)
    pos = add(struct.pack("<%df" % (3 * n), *[v for p in rig.pos for v in p]), "VEC3", 5126, n, None)
    accessors[pos]["min"] = [min(p[k] for p in rig.pos) for k in range(3)]
    accessors[pos]["max"] = [max(p[k] for p in rig.pos) for k in range(3)]
    nrm = add(struct.pack("<%df" % (3 * n), *[v for p in rig.nrm for v in p]), "VEC3", 5126, n, None)
    uv = add(struct.pack("<%df" % (2 * n), *[v for p in rig.uvs for v in p]), "VEC2", 5126, n, None)
    # Rigid box parts use one joint; Blender-built meshes carry four influences.
    joints4 = getattr(rig, "jnt4", None) or [(j, 0, 0, 0) for j in rig.jnt]
    weights4 = getattr(rig, "w4", None) or [(1.0, 0.0, 0.0, 0.0) for _ in rig.jnt]
    jnt = add(struct.pack("<%dH" % (4 * n), *[v for j in joints4 for v in j]), "VEC4", 5123, n, None)
    wgt = add(struct.pack("<%df" % (4 * n), *[v for w in weights4 for v in w]), "VEC4", 5126, n, None)
    idx = add(struct.pack("<%dH" % len(rig.idx), *rig.idx), "SCALAR", 5123, len(rig.idx), None)
    inv = []
    for wpos in rig.world:
        inv += [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, -wpos[0], -wpos[1], -wpos[2], 1]
    ibm = add(struct.pack("<%df" % len(inv), *inv), "MAT4", 5126, len(rig.world), None)
    samplers, channels = [], []
    for joint, path_, times, values in tracks:
        ti = add(struct.pack("<%df" % len(times), *times), "SCALAR", 5126, len(times), None)
        accessors[ti]["min"] = [times[0]]
        accessors[ti]["max"] = [times[-1]]
        width = 4 if path_ == "rotation" else 3
        vi = add(struct.pack("<%df" % (width * len(values)), *[v for row in values for v in row]),
                 "VEC4" if width == 4 else "VEC3", 5126, len(values), None)
        samplers.append({"input": ti, "output": vi, "interpolation": "LINEAR"})
        channels.append({"sampler": len(samplers) - 1, "target": {"node": rig.index[joint], "path": path_}})
    nodes = []
    for i, name in enumerate(rig.names):
        node = {"name": name, "translation": rig.t[i]}
        children = [k for k, p in enumerate(rig.parent) if p == i]
        if children:
            node["children"] = children
        nodes.append(node)
    nodes.append({"name": "mesh", "mesh": 0, "skin": 0})
    roots = [i for i, p in enumerate(rig.parent) if p < 0] + [len(nodes) - 1]
    doc = {
        "asset": {"version": "2.0", "generator": "n3e ashgrave original generator"},
        "scene": 0, "scenes": [{"nodes": roots}], "nodes": nodes,
        "meshes": [{"primitives": [{"attributes": {"POSITION": pos, "NORMAL": nrm, "TEXCOORD_0": uv,
                                                   "JOINTS_0": jnt, "WEIGHTS_0": wgt},
                                    "indices": idx, "material": 0}]}],
        "skins": [{"joints": list(range(len(rig.names))), "inverseBindMatrices": ibm}],
        "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
        "textures": [{"source": 0}], "images": [{"uri": texture}],
        "buffers": [{"uri": path.stem + ".buffer", "byteLength": len(blob)}],
        "bufferViews": views, "accessors": accessors,
        "animations": [{"samplers": samplers, "channels": channels}] if tracks else [],
    }
    if not tracks:
        del doc["animations"]
    path.write_text(json.dumps(doc))
    path.with_name(path.stem + ".buffer").write_bytes(bytes(blob))
    del attachment, duration


def clip(rig, duration, frames, pose):
    """Sample pose(t) -> {joint: (euler angles or quaternion, translation or None)}."""
    times = [duration * i / frames for i in range(frames + 1)]
    samples = [pose(t) for t in times]
    tracks = []
    for joint in rig.names:
        rot = [s.get(joint, {}).get("r") for s in samples]
        if any(r is not None for r in rot):
            tracks.append((joint, "rotation", times, [euler(*(r or (0, 0, 0))) for r in rot]))
        tr = [s.get(joint, {}).get("t") for s in samples]
        if any(v is not None for v in tr):
            base = rig.t[rig.index[joint]]
            tracks.append((joint, "translation", times,
                           [[base[k] + (v[k] if v else 0) for k in range(3)] for v in tr]))
    return tracks


def investigator():
    rng = random.Random(3)
    pal = Palette()
    colors = [("coat", (138, 112, 72)), ("coat_dark", (96, 78, 50)), ("suit", (34, 34, 40)),
              ("shirt", (200, 196, 184)), ("tie", (120, 22, 28)), ("skin", (196, 150, 120)),
              ("hair", (70, 52, 36)), ("shoe", (22, 18, 16)), ("smoke", (160, 160, 170))]
    for i, (name, c) in enumerate(colors):
        pal.swatch(name, i, c, rng)
    # Face (swatch 16..): skin with eyes, brows, a hard mouth and stubble.
    fx, fy = 0, 16
    pal.c.rect(fx, fy, fx + 16, fy + 16, (196, 150, 120))
    for x, y, c in [(4, 6, (30, 30, 30)), (11, 6, (30, 30, 30)), (3, 5, (70, 52, 36)), (4, 5, (70, 52, 36)),
                    (5, 5, (70, 52, 36)), (10, 5, (70, 52, 36)), (11, 5, (70, 52, 36)), (12, 5, (70, 52, 36))]:
        pal.c.set(fx + x, fy + y, c)
    pal.c.rect(fx + 6, fy + 11, fx + 10, fy + 12, (110, 60, 50))
    for _ in range(18):
        pal.c.set(fx + rng.randint(3, 12), fy + rng.randint(10, 14), (150, 118, 96))
    pal.c.rect(fx, fy, fx + 16, fy + 3, (70, 52, 36))   # hairline
    pal.slots["face"] = (fx, fy)
    # Chest front: open coat over white shirt and a loosened crimson tie.
    cx, cy = 16, 16
    pal.c.rect(cx, cy, cx + 16, cy + 16, (138, 112, 72))
    pal.c.rect(cx + 5, cy, cx + 11, cy + 16, (200, 196, 184))
    pal.c.rect(cx + 7, cy + 2, cx + 9, cy + 13, (120, 22, 28))
    pal.c.rect(cx + 4, cy, cx + 5, cy + 16, (96, 78, 50))
    pal.c.rect(cx + 11, cy, cx + 12, cy + 16, (96, 78, 50))
    pal.slots["chest"] = (cx, cy)
    rig = Rig([("hips", -1, [0, .98, 0]), ("spine", 0, [0, .14, 0]), ("chest", 1, [0, .26, 0]),
               ("head", 2, [0, .3, 0]), ("arm_r", 2, [.23, .2, 0]), ("fore_r", 4, [0, -.3, 0]),
               ("arm_l", 2, [-.23, .2, 0]), ("fore_l", 6, [0, -.3, 0]), ("thigh_r", 0, [.1, -.02, 0]),
               ("shin_r", 8, [0, -.44, 0]), ("thigh_l", 0, [-.1, -.02, 0]), ("shin_l", 10, [0, -.44, 0]),
               ("coat", 0, [0, 0, 0])])
    W = rig.world
    full = lambda name: pal.uv(name)  # noqa: E731
    face_uv = [(pal.slots["face"][0] + 1) / 64, (pal.slots["face"][1] + 1) / 64,
               (pal.slots["face"][0] + 15) / 64, (pal.slots["face"][1] + 15) / 64]
    chest_uv = [pal.slots["chest"][0] / 64, pal.slots["chest"][1] / 64,
                (pal.slots["chest"][0] + 16) / 64, (pal.slots["chest"][1] + 16) / 64]
    hx = W[0]
    rig.box("hips", [0, hx[1] + .02, 0], [.36, .2, .22], full("suit"))
    rig.box("spine", [0, W[1][1] + .1, 0], [.4, .24, .24], full("coat"), chest_uv)
    rig.box("chest", [0, W[2][1] + .1, 0], [.48, .3, .27], full("coat"), chest_uv)
    rig.box("chest", [0, W[2][1] + .26, .02], [.5, .1, .3], full("coat_dark"))          # collar
    rig.box("head", [0, W[3][1] + .12, 0], [.22, .26, .24], full("skin"), face_uv)
    rig.box("head", [0, W[3][1] + .27, .02], [.24, .07, .26], full("hair"))
    for side in ("r", "l"):
        s = 1 if side == "r" else -1
        a, fo = W[rig.index["arm_" + side]], W[rig.index["fore_" + side]]
        rig.box("arm_" + side, [a[0] + .02 * s, a[1] - .14, 0], [.13, .32, .14], full("coat"))
        rig.box("fore_" + side, [fo[0] + .02 * s, fo[1] - .13, 0], [.12, .28, .13], full("coat"))
        rig.box("fore_" + side, [fo[0] + .02 * s, fo[1] - .31, 0], [.08, .09, .08], full("skin"))
        t, sh = W[rig.index["thigh_" + side]], W[rig.index["shin_" + side]]
        rig.box("thigh_" + side, [t[0], t[1] - .22, 0], [.15, .44, .16], full("suit"))
        rig.box("shin_" + side, [sh[0], sh[1] - .22, 0], [.13, .44, .14], full("suit"))
        rig.box("shin_" + side, [sh[0], sh[1] - .47, -.04], [.14, .07, .24], full("shoe"))
    # Coat skirt: front halves split so legs show, back panel full.
    rig.box("coat", [0, hx[1] - .2, .08], [.5, .56, .1], full("coat"))
    rig.box("coat", [.17, hx[1] - .2, -.03], [.16, .56, .16], full("coat"))
    rig.box("coat", [-.17, hx[1] - .2, -.03], [.16, .56, .16], full("coat"))
    return rig, pal


def imp():
    rng = random.Random(11)
    pal = Palette()
    for i, (name, c) in enumerate([("hide", (140, 30, 26)), ("hide_dark", (80, 14, 16)), ("horn", (30, 24, 20)),
                                   ("claw", (220, 210, 170)), ("belly", (170, 70, 50))]):
        pal.swatch(name, i, c, rng, .15)
    fx, fy = 0, 16
    pal.c.rect(fx, fy, fx + 16, fy + 16, (140, 30, 26))
    for x, y in [(3, 6), (4, 6), (11, 6), (12, 6), (4, 7), (11, 7)]:
        pal.c.set(fx + x, fy + y, (250, 220, 40))
    pal.c.rect(fx + 4, fy + 11, fx + 12, fy + 13, (30, 8, 8))
    for x in (5, 7, 9, 11):
        pal.c.set(fx + x, fy + 11, (230, 230, 200))
    pal.slots["face"] = (fx, fy)
    rig = Rig([("hips", -1, [0, .55, 0]), ("spine", 0, [0, .1, .02]), ("chest", 1, [0, .16, -.04]),
               ("head", 2, [0, .2, -.06]), ("arm_r", 2, [.18, .08, 0]), ("fore_r", 4, [0, -.22, 0]),
               ("arm_l", 2, [-.18, .08, 0]), ("fore_l", 6, [0, -.22, 0]), ("thigh_r", 0, [.09, -.02, 0]),
               ("shin_r", 8, [0, -.26, 0]), ("thigh_l", 0, [-.09, -.02, 0]), ("shin_l", 10, [0, -.26, 0]),
               ("tail", 0, [0, 0, .12])])
    W = rig.world
    full = pal.uv
    face_uv = [1 / 64, 17 / 64, 15 / 64, 31 / 64]
    rig.box("hips", [0, W[0][1], .02], [.28, .16, .2], full("hide"))
    rig.box("spine", [0, W[1][1] + .08, 0], [.3, .18, .22], full("belly"))
    rig.box("chest", [0, W[2][1] + .08, -.02], [.38, .22, .26], full("hide"))
    rig.box("head", [0, W[3][1] + .09, -.05], [.26, .22, .24], full("hide"), face_uv)
    for s in (1, -1):
        rig.box("head", [.1 * s, W[3][1] + .24, -.02], [.05, .14, .05], full("horn"))
        rig.box("head", [.14 * s, W[3][1] + .31, .01], [.04, .07, .04], full("horn"))
    for side in ("r", "l"):
        s = 1 if side == "r" else -1
        a, fo = W[rig.index["arm_" + side]], W[rig.index["fore_" + side]]
        rig.box("arm_" + side, [a[0] + .02 * s, a[1] - .1, 0], [.09, .24, .1], full("hide"))
        rig.box("fore_" + side, [fo[0] + .02 * s, fo[1] - .12, 0], [.08, .26, .09], full("hide_dark"))
        rig.box("fore_" + side, [fo[0] + .02 * s, fo[1] - .28, -.03], [.1, .06, .12], full("claw"))
        t, sh = W[rig.index["thigh_" + side]], W[rig.index["shin_" + side]]
        rig.box("thigh_" + side, [t[0], t[1] - .13, .02], [.11, .26, .12], full("hide"))
        rig.box("shin_" + side, [sh[0], sh[1] - .13, .02], [.09, .26, .1], full("hide_dark"))
        rig.box("shin_" + side, [sh[0], sh[1] - .27, -.03], [.11, .05, .16], full("claw"))
    tl = W[rig.index["tail"]]
    rig.box("tail", [0, tl[1] - .05, tl[2] + .18], [.06, .06, .36], full("hide_dark"))
    rig.box("tail", [0, tl[1] - .05, tl[2] + .4], [.1, .1, .08], full("horn"))
    return rig, pal


TAU = 2 * math.pi


def investigator_clips():
    def idle(t):
        b = math.sin(TAU * t / 2.0)
        return {"chest": {"r": (.03 * b, 0, 0)}, "head": {"r": (0, .15 * math.sin(TAU * t / 4.0), 0)},
                "arm_r": {"r": (.05, 0, .06)}, "arm_l": {"r": (.05, 0, -.06)}, "coat": {"r": (.02 * b, 0, 0)}}

    def gait(t, period, amp, lean=0.0, sign=1):
        p = sign * TAU * t / period
        s = math.sin(p)
        return {"hips": {"t": (0, .04 * abs(math.cos(p)) * amp, 0)},
                "spine": {"r": (-lean, 0, 0)},
                "thigh_r": {"r": (.6 * amp * s, 0, 0)}, "thigh_l": {"r": (-.6 * amp * s, 0, 0)},
                "shin_r": {"r": (-.7 * amp * max(0, -math.cos(p)), 0, 0)},
                "shin_l": {"r": (-.7 * amp * max(0, math.cos(p)), 0, 0)},
                "arm_r": {"r": (-.5 * amp * s, 0, .05)}, "arm_l": {"r": (.5 * amp * s, 0, -.05)},
                "fore_r": {"r": (.3 * amp, 0, 0)}, "fore_l": {"r": (.3 * amp, 0, 0)},
                "coat": {"r": (.25 * amp * abs(s) + lean * .5, 0, 0)}}

    def attack(t):
        # Wind up, then thrust the right hand forward to cast; strike at 0.4 s.
        k = min(1, t / .4)
        wind = math.sin(math.pi * min(1, t / .25)) * (1 - k)
        thrust = math.sin(math.pi * min(1, max(0, (t - .2) / .5)))
        return {"spine": {"r": (-.1 * thrust, .3 * wind - .25 * thrust, 0)},
                "arm_r": {"r": (-.6 * wind + 1.45 * thrust, 0, .1)}, "fore_r": {"r": (.4 * wind + .1 * thrust, 0, 0)},
                "arm_l": {"r": (.5 * thrust, 0, -.3 * thrust)}, "fore_l": {"r": (.9 * thrust, 0, 0)},
                "thigh_r": {"r": (-.2 * thrust, 0, 0)}, "thigh_l": {"r": (.25 * thrust, 0, 0)}}

    def death(t):
        k = min(1, t / 1.0)
        e = 1 - (1 - k) ** 2
        return {"hips": {"r": (1.45 * e, 0, 0), "t": (0, -.78 * e, .35 * e)},
                "spine": {"r": (.1 * e, 0, 0)}, "head": {"r": (.3 * e, .4 * e, 0)},
                "arm_r": {"r": (-1.2 * e, 0, .6 * e)}, "arm_l": {"r": (-1.0 * e, 0, -.5 * e)},
                "thigh_r": {"r": (-.2 * e, 0, 0)}, "thigh_l": {"r": (.1 * e, 0, 0)},
                "shin_r": {"r": (-.4 * e, 0, 0)}}

    def ready(t):
        b = math.sin(TAU * t / 1.2)
        return {"spine": {"r": (-.08, 0, 0)}, "arm_r": {"r": (.7, 0, .15)}, "fore_r": {"r": (.9 + .05 * b, 0, 0)},
                "arm_l": {"r": (.55, 0, -.2)}, "fore_l": {"r": (1.1, 0, 0)},
                "thigh_r": {"r": (-.12, 0, 0)}, "thigh_l": {"r": (.12, 0, 0)}, "chest": {"r": (.02 * b, 0, 0)}}
    return [(2.0, 16, idle, [-1, -1]), (1.0, 16, lambda t: gait(t, 1.0, .8), [-1, -1]),
            (1.0, 16, attack, [.4, -1]), (1.2, 12, death, [-1, -1]),
            (.6, 12, lambda t: gait(t, .6, 1.25, lean=.22), [-1, -1]),
            (1.0, 16, lambda t: gait(t, 1.0, .6, sign=-1), [-1, -1]), (1.2, 12, ready, [-1, -1])]


def imp_clips():
    def idle(t):
        b = math.sin(TAU * t / 1.6)
        return {"hips": {"t": (0, .02 * b, 0)}, "chest": {"r": (.12 + .05 * b, 0, 0)},
                "head": {"r": (-.1, .3 * math.sin(TAU * t / 3.2), 0)}, "tail": {"r": (.2, .5 * b, 0)},
                "arm_r": {"r": (.3, 0, .15)}, "arm_l": {"r": (.3, 0, -.15)}}

    def walk(t):
        p = TAU * t / .8
        s = math.sin(p)
        return {"hips": {"t": (0, .03 * abs(math.cos(p)), 0)}, "chest": {"r": (.25, 0, .1 * s)},
                "thigh_r": {"r": (.7 * s, 0, 0)}, "thigh_l": {"r": (-.7 * s, 0, 0)},
                "shin_r": {"r": (-.8 * max(0, -math.cos(p)), 0, 0)}, "shin_l": {"r": (-.8 * max(0, math.cos(p)), 0, 0)},
                "arm_r": {"r": (.5 - .5 * s, 0, .2)}, "arm_l": {"r": (.5 + .5 * s, 0, -.2)},
                "tail": {"r": (.3, .6 * s, 0)}}

    def attack(t):
        up = math.sin(math.pi * min(1, t / .3))
        slash = math.sin(math.pi * min(1, max(0, (t - .3) / .35)))
        return {"chest": {"r": (-.3 * up + .5 * slash, 0, 0)}, "hips": {"t": (0, .05 * up, -.1 * slash)},
                "arm_r": {"r": (-1.8 * up + 2.2 * slash, 0, .2)}, "arm_l": {"r": (-1.6 * up + 2.0 * slash, 0, -.2)},
                "fore_r": {"r": (.6 * up, 0, 0)}, "fore_l": {"r": (.6 * up, 0, 0)}, "tail": {"r": (.6 * up, 0, 0)}}

    def death(t):
        e = 1 - (1 - min(1, t / 1.0)) ** 2
        return {"hips": {"r": (-1.4 * e, .5 * e, 0), "t": (0, -.42 * e, -.2 * e)},
                "head": {"r": (-.4 * e, 0, .3 * e)}, "arm_r": {"r": (1.5 * e, 0, .8 * e)},
                "arm_l": {"r": (1.2 * e, 0, -.9 * e)}, "tail": {"r": (-.5 * e, .4 * e, 0)},
                "thigh_r": {"r": (.9 * e, 0, 0)}, "shin_r": {"r": (-1.0 * e, 0, 0)}}
    return [(1.6, 16, idle, [-1, -1]), (.8, 16, walk, [-1, -1]), (.9, 18, attack, [.45, -1]),
            (1.2, 12, death, [-1, -1])]


# ---------------------------------------------------------------- Blender-refined investigator

def refined_investigator():
    """Model, weight, unwrap and bake the investigator in Blender (KO-style low poly).

    The mesh is built on the same 13-joint rig as the procedural figure, so the
    scripted clips apply unchanged.
    """
    import character_import
    import subprocess
    out = SRC / "refined"
    run = subprocess.run([str(character_import.BLENDER), "-b", "--factory-startup", "--python",
                          "tools/assetc/blender/investigator.py", "--", str(out)], capture_output=True, text=True)
    if run.returncode or "INVESTIGATOR" not in run.stdout:
        raise RuntimeError(run.stdout[-3000:] + run.stderr[-3000:])
    data = json.loads((out / "investigator.json").read_text())
    rig, _ = investigator()
    if data["joints"] != rig.names:
        raise ValueError("refined investigator joints differ from the rig")
    rig.pos = [v["p"] for v in data["vertices"]]
    rig.nrm = [v["n"] for v in data["vertices"]]
    rig.uvs = [v["uv"] for v in data["vertices"]]
    rig.jnt4 = [tuple(v["j"]) for v in data["vertices"]]
    rig.w4 = [tuple(v["w"]) for v in data["vertices"]]
    rig.jnt = [j[0] for j in rig.jnt4]
    rig.idx = [i for tri in data["triangles"] for i in tri]
    character_import.texture(out / "investigator-bake.png", SRC / "investigator-refined.png", 256)
    return rig, "investigator-refined.png"


def measured_rig(data):
    """The Ashgrave rig with rest positions measured on a Blender-mapped body."""
    base, _ = investigator()
    if data["joints"] != base.names:
        raise ValueError("mapped investigator joints differ from the rig")
    # Same joint names and hierarchy, rest positions measured on this body.
    pos = data["positions"]
    rig = Rig([(n, base.parent[i], [pos[n][k] - (pos[base.names[base.parent[i]]][k] if base.parent[i] >= 0 else 0)
                                    for k in range(3)]) for i, n in enumerate(base.names)])
    rig.pos = [v["p"] for v in data["vertices"]]
    rig.nrm = [v["n"] for v in data["vertices"]]
    rig.uvs = [v["uv"] for v in data["vertices"]]
    rig.jnt4 = [tuple(v["j"]) for v in data["vertices"]]
    rig.w4 = [tuple(v["w"]) for v in data["vertices"]]
    rig.jnt = [j[0] for j in rig.jnt4]
    rig.idx = [i for tri in data["triangles"] for i in tri]
    return rig


def mpfb_investigator():
    """MakeHuman (MPFB2 + CC0 system assets) investigator, mapped onto the Ashgrave rig.

    Needs `tools/install-blender.sh` plus MPFB and the MakeHuman system assets in
    the tool-local Blender profile (see the evidence record).
    """
    import character_import
    import os
    import subprocess
    out = SRC / "mpfb"
    env = dict(os.environ, BLENDER_USER_RESOURCES=str(Path(".cache/tools/blender-user").resolve()))
    run = subprocess.run([str(character_import.BLENDER), "-b", "--factory-startup", "--python",
                          "tools/assetc/blender/mpfb_investigator.py", "--", str(out)], capture_output=True, text=True, env=env)
    if run.returncode or "MPFB INVESTIGATOR" not in run.stdout:
        raise RuntimeError(run.stdout[-3000:] + run.stderr[-3000:])
    rig = measured_rig(json.loads((out / "investigator.json").read_text()))
    # KO's player textures carry about 230 texels per metre; 512 px here gives ~200.
    character_import.texture(out / "investigator-bake.png", SRC / "investigator-mpfb.png", 512, painted=True)
    return rig, "investigator-mpfb.png"


# Synty POLYGON Starter Pack (free, Synty One-Time Purchase Licence): source files
# are licensed per team, so they are unpacked from the user's download into
# build/synty and never committed.
SYNTY = Path("build/synty/SourceFiles")
SYNTY_ZIP_SHA256 = "5551d93cdd7b31f51bea4ca22dec6b162bdf71391b1e6f954d037e60a33af8cd"   # v2


def synty_investigator():
    """The Starter Pack's base male, dressed from the Synty palette, on the Ashgrave rig."""
    import character_import
    import hashlib
    import os
    import subprocess
    import zipfile
    if not SYNTY.is_dir():
        archive = Path(os.environ.get("SYNTY_STARTER_ZIP", "~/Downloads/POLYGON_Starter_SourceFiles_v2.zip")).expanduser()
        if not archive.is_file():
            raise FileNotFoundError(f"{archive}: download the free POLYGON Starter Pack source files from "
                                    "syntystore.com (or set SYNTY_STARTER_ZIP)")
        if hashlib.sha256(archive.read_bytes()).hexdigest() != SYNTY_ZIP_SHA256:
            raise ValueError(f"{archive}: not the pinned POLYGON_Starter_SourceFiles_v2.zip")
        with zipfile.ZipFile(archive) as z:
            z.extractall(SYNTY.parent)
    out = SRC / "synty"
    run = subprocess.run([str(character_import.BLENDER), "-b", "--factory-startup", "--python",
                          "tools/assetc/blender/synty_investigator.py", "--", str(SYNTY / "FBX/Characters.fbx"),
                          str(out), "--paint=1"], capture_output=True, text=True)
    if run.returncode or "SYNTY INVESTIGATOR" not in run.stdout:
        raise RuntimeError(run.stdout[-3000:] + run.stderr[-3000:])
    rig = measured_rig(json.loads((out / "investigator.json").read_text()))
    # A flat-colour palette: 512 px keeps every sampled swatch intact.
    character_import.texture(SYNTY / "Textures/PolygonStarter_Texture_01.png", SRC / "investigator-synty.png", 512)
    return rig, "investigator-synty.png"


# Shadow Tower (PS1, FromSoftware) ghoul, read from the user's own disc image by
# `shadow_tower.py`: the game's model, texture, skeleton and animation. Local
# only: extracted sources and cooked clips stay in build/ and are never committed.
GHOUL = ("ST/CHR1/M12.T", 20, {"idle": 0, "walk": 1, "attack": 2, "death": 6})


def shadow_tower_ghoul():
    import shadow_tower
    file, entry, clips = GHOUL
    group = shadow_tower.entries(shadow_tower.disc().read(file))[entry:entry + 5]
    results, triangles, height = shadow_tower.export(group, SRC / "shadow-tower", clips)
    scale = round(1.8 / height, 4)                     # about 2.27 m in the game's units
    for state in clips:
        cooked, _ = gltf.cook(SRC, f"shadow-tower/npc-{state}.gltf", {"instance_scale": [scale] * 3, "attachment_node": 0})
        (SRC / f"npc-{state}.bin").write_bytes(cooked)
    animation = [{"duration": results[state][0], "blend": .2, "loop_blend": False,
                  "markers": [results[state][1], -1] if state == "attack" else [-1, -1]} for state in clips]
    print("shadow tower ghoul", triangles, "triangles, scale", scale)
    return animation, scale, results["attack"][1]


# Demon's Souls (PS3, FromSoftware) soldier c2010 with its kettle helmet, shield and
# short spear, read from the user's own dump by `demons_souls.py`; the Havok wavelet
# animation is decoded by `havok.py`. Local only, never committed.
SOLDIER = ("c2010", {"idle": "a00_0000", "walk": "a00_0200", "attack": "a00_3000", "death": "a00_2200"},
           {"c2010_body", "HD_F_8000_L", "WP_A_1509_L_shield", "WP_A_0700_L_short_spear"})


def demons_souls_soldier():
    import demons_souls
    demons_souls.ensure_usrdir()
    char, clips, textures = SOLDIER
    results, triangles, height = demons_souls.package(char, clips, SRC / "demons-souls", textures)
    scale = round(1.8 / height, 4)
    for state in clips:
        cooked, _ = gltf.cook(SRC, f"demons-souls/npc-{state}.gltf", {"instance_scale": [scale] * 3, "attachment_node": 0})
        (SRC / f"npc-{state}.bin").write_bytes(cooked)
    animation = [{"duration": results[state][0], "blend": .2, "loop_blend": False,
                  "markers": [results[state][1], -1] if state == "attack" else [-1, -1]} for state in clips]
    print("demon's souls soldier", triangles, "triangles, scale", scale)
    return animation, scale, results["attack"][1]



# Demon's Souls level 1-1 (Gates of Boletaria, m02_00_00_00), cropped to the start
# and the first soldier courtyards, from the user's own dump. Local only.
LEVEL = ("m02_00_00_00", (-70, 70, -175, -20))


def ground(triangles, x, z):
    """Heights of every collision surface above (x, z), highest first."""
    out = []
    for a, b, c in triangles:
        d = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
        if abs(d) < 1e-9:
            continue
        l1 = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / d
        l2 = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / d
        l3 = 1 - l1 - l2
        if min(l1, l2, l3) >= 0:
            out.append(l1 * a[1] + l2 * b[1] + l3 * c[1])
    return sorted(out, reverse=True)


def demons_souls_level(npc_model="c2010", count=10):
    import demons_souls
    map_id, box = LEVEL
    level = demons_souls.level(map_id, box)
    xs, ys, zs = zip(*level["positions"])
    center = [(min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2]
    radius = max(math.dist(center, p) for p in level["positions"])
    lod = (b"N3L1" + u(1) + f(center) + f([radius, 1.0]) + u(0) + u(1) + f([0.0])
           + u(len(level["indices"])) + struct.pack("<%dI" % len(level["indices"]), *level["indices"]))
    tris = []
    for tri in level["collision"]:                  # millimetres keep scene.json under the 16 MiB file limit
        tri = [[round(v, 3) for v in q] for q in tri]
        ab = [tri[1][k] - tri[0][k] for k in range(3)]
        ac = [tri[2][k] - tri[0][k] for k in range(3)]
        cross = [ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2], ab[0] * ac[1] - ab[1] * ac[0]]
        if sum(x * x for x in cross) > 1e-8:
            tris.append(tri)

    def standable(pos):
        # The server spawns on the highest surface; keep placements that are on it.
        tops = ground(tris, pos[0], pos[2])
        return tops and abs(tops[0] - pos[1]) < 1.0
    starts = [p["pos"] for p in level["placements"] if p["type"] == 4 and standable(p["pos"])]
    if not starts:
        raise ValueError("no standable player start in the crop")
    start = starts[0]
    enemies = sorted((p["pos"] for p in level["placements"] if p["model"] == npc_model and standable(p["pos"])),
                     key=lambda q: math.dist(q, start))[:count]
    low = min(ys) - 100
    heightfield = {"width": 2, "depth": 2, "origin": [min(xs), low, min(zs)], "spacing": 1.0,
                   "heights": [0.0] * 4, "diagonal": "fixed"}
    print("demon's souls level", map_id, level["triangles"], "triangles,", level["vertices"], "vertices,",
          level["textures"], "textures, grid", level["grid"], "m;", len(tris), "collision triangles;",
          len(enemies), npc_model, "spawns")
    return {"world": level["world"], "lod": lod, "collision": [v for t in tris for v in t], "heightfield": heightfield,
            "player_spawn": (start[0], start[2]), "spawns": [(q[0], q[2]) for q in enemies],
            "effigy": [start[0] + 1.5, start[1], start[2] + 1.5]}


# The Demon's Souls player (c0000 skeleton and clips) in armour set 8100 (crested helm)
# with a short sword on R_Weapon, from the user's own dump. Local only.
DES_PLAYER = ({"idle": "a00_0000", "walk": "a00_0200", "attack": "a20_3000", "death": "a00_6010",
               "run": "a00_0300", "backward": "a00_0201", "ready": "a00_0001"},
              [f"{k}_m_8100" for k in ("hd", "bd", "am", "lg")] + ["wp_a_0200@R_Weapon"])


def demons_souls_player():
    import demons_souls
    demons_souls.ensure_usrdir(("chr", "parts"))
    clips, parts = DES_PLAYER
    results, triangles, _ = demons_souls.package("c0000", clips, SRC / "demons-souls-player", None, "player", parts=parts)
    names = [n["name"] for n in json.loads((SRC / "demons-souls-player/player-idle.gltf").read_text())["nodes"]]
    hand = names.index("R_Weapon")
    for state in clips:
        cooked, _ = gltf.cook(SRC, f"demons-souls-player/player-{state}.gltf", {"instance_scale": [1, 1, 1], "attachment_node": hand})
        (SRC / f"player-{state}.bin").write_bytes(cooked)
    print("demon's souls player", triangles, "triangles")
    return [{"duration": results[state][0], "blend": .2, "loop_blend": False,
             "markers": [results[state][1], -1] if state == "attack" else [-1, -1]} for state in clips]

ENEMIES = {
    "shadow-tower": (shadow_tower_ghoul, "ghoul", "shadow-tower/npc-idle.gltf",
                     "Enemy: the ghoul from Shadow Tower (FromSoftware, 1999; NTSC-U SLUS-00863), read from the\n"
                     "user's own disc image (ST/CHR1/M12.T entry 20: model, texture, skeleton and animation).\n"),
    "demons-souls": (demons_souls_soldier, "soldier", "demons-souls/npc-idle.gltf",
                     "Enemy: the soldier from Demon's Souls (FromSoftware, 2009; PS3 BLES00932), read from the\n"
                     "user's own dump (chr/c2010: model, textures, skeleton and Havok animation a00_0000/0200/\n"
                     "3000/2200, decoded by tools/assetc/havok.py).\n"),
}


# Meshy text-to-3D detective (meshy-6), auto-rigged and animated by Meshy; one
# clip per downloaded GLB. Sources live in build/meshy/anim (paid, not committed).
MESHY_CLIPS = {"idle": "idle.glb", "walk": "walk.glb", "attack": "cast.glb", "death": "death.glb",
               "run": "run.glb", "backward": "backward.glb", "ready": "ready.glb"}
MESHY_SPEEDS = {"attack": 2.4, "death": 2.0}   # 2.7 s cast -> ~1 s hex cadence; 6.3 s fall -> 3.2 s


def meshy_detective():
    import character_import
    source = Path("build/meshy/anim")
    out = SRC / "characters"
    durations = {}
    for state, name in MESHY_CLIPS.items():
        durations.update(character_import.export(source / name, out, "player", {state: "*"},
                                                 texture_source=Path("build/meshy/detective-textured_base_color.png"),
                                                 size=512, speeds=MESHY_SPEEDS))
    names = [n.get("name") for n in json.loads((out / "player-idle.gltf").read_text())["nodes"]]
    attachment = names.index("RightHand")
    for state in MESHY_CLIPS:
        cooked, _ = gltf.cook(SRC, f"characters/player-{state}.gltf",
                              {"instance_scale": [1.06] * 3, "attachment_node": attachment})
        (SRC / f"player-{state}.bin").write_bytes(cooked)
    animation = []
    for state in MESHY_CLIPS:
        d = round(durations[state], 6)
        animation.append({"duration": d, "blend": .2, "loop_blend": False,
                          "markers": [round(d * .5, 4), -1] if state == "attack" else [-1, -1]})
    return animation


def imp_png():
    rig, pal = imp()
    (SRC / "imp.png").write_bytes(png_rgb(64, 64, pal.rgb()))
    return rig, "imp.png"


# ---------------------------------------------------------------- CC0 characters via Blender

KAYKIT = Path("build/external")
PLAYER_CLIPS = {"idle": "Idle", "walk": "Walking_A", "attack": "Spellcast_Shoot", "death": "Death_A",
                "run": "Running_A", "backward": "Walking_Backwards", "ready": "Spellcasting"}
NPC_CLIPS = {"idle": "Idle", "walk": "Walking_D_Skeletons", "attack": "1H_Melee_Attack_Chop",
             "death": "Death_C_Skeletons"}


def kaykit_characters():
    """CC0 KayKit characters (Kay Lousberg) through Blender into the gltf.cook subset.

    Sources are cloned, not committed: KayKit-Character-Pack-Adventures-1.0 (hooded
    rogue as the investigator) and KayKit-Character-Pack-Skeletons-1.0 (minion as
    the revenant) under build/external.
    """
    import character_import
    import subprocess
    # Opt-in, pinned CC0 sources; fetched only for this variant, never committed.
    for repo, commit in (("KayKit-Character-Pack-Adventures-1.0", "672074b73ba276876a19e8816ecdc5241817ab47"),
                         ("KayKit-Character-Pack-Skeletons-1.0", "15b62b9bad122f72926c10fb14d622c73819fa54")):
        target = KAYKIT / repo
        if not target.is_dir():
            KAYKIT.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "clone", "-q", f"https://github.com/KayKit-Game-Assets/{repo}.git", str(target)], check=True)
            subprocess.run(["git", "-C", str(target), "checkout", "-q", commit], check=True)
        if "CC0" not in (target / "LICENSE.txt").read_text():
            raise RuntimeError(f"{repo}: expected a CC0 licence")
    adventurers = KAYKIT / "KayKit-Character-Pack-Adventures-1.0/addons/kaykit_character_pack_adventures/Characters/gltf"
    skeletons = KAYKIT / "KayKit-Character-Pack-Skeletons-1.0/addons/kaykit_character_pack_skeletons/Characters/gltf"
    out = SRC / "characters"
    player = character_import.export(adventurers / "Rogue_Hooded.glb", out, "player", PLAYER_CLIPS,
                                     keep_rigid=["Rogue_Cape"], texture_source=adventurers / "rogue_texture.png",
                                     recolor=(.22, .55, .095, .55))   # green cloth -> weathered khaki
    npc = character_import.export(skeletons / "Skeleton_Minion.glb", out, "npc", NPC_CLIPS,
                                  texture_source=skeletons / "skeleton_texture.png")
    # Source characters are about 2.2 m; n3e movement capsules are 1.6 m.
    scale = {"player": .8, "npc": .78}
    attachment = {}
    for prefix, clips in (("player", PLAYER_CLIPS), ("npc", NPC_CLIPS)):
        names = [n.get("name") for n in json.loads((out / f"{prefix}-idle.gltf").read_text())["nodes"]]
        attachment[prefix] = names.index("handslot.r")
        for state in clips:
            meta = {"instance_scale": [scale[prefix]] * 3, "attachment_node": attachment[prefix]}
            cooked, _ = gltf.cook(SRC, f"characters/{prefix}-{state}.gltf", meta)
            (SRC / f"{prefix}-{state}.bin").write_bytes(cooked)
    animation = []
    for durations, clips in ((player, PLAYER_CLIPS), (npc, NPC_CLIPS)):
        for state in clips:
            d = round(durations[state], 6)
            strike = [round(d * .55, 4), -1] if state == "attack" else [-1, -1]
            animation.append({"duration": d, "blend": .2, "loop_blend": False, "markers": strike})
    return animation, attachment["npc"], scale["npc"]


# ---------------------------------------------------------------- HUD

def hud_art():
    """Optional Meshy-generated HUD art (ASHGRAVE_HUD=meshy), prepared in build/meshy/hud."""
    import os
    import subprocess
    if os.environ.get("ASHGRAVE_HUD") != "meshy":
        return None
    folder = Path("build/meshy/hud")
    art = {}
    for name, file in (("frame", "panel-cut.png"), ("bar", "bar-cut.png"), ("icons", "icons-atlas.png"),
                       ("leather", "leather-512.png")):
        w, h = (int(v) for v in subprocess.check_output(["magick", "identify", "-format", "%w %h", str(folder / file)], text=True).split())
        if w > 1024 or h > 1024:
            raise ValueError(f"{file}: HUD textures are at most 1024 px")
        art[name] = (w, h, subprocess.check_output(["magick", str(folder / file), "-depth", "8", "RGBA:-"]))
    return art


def hud(root):
    alphabet = re.findall(r'"([01/]{41})"', Path("client/render/hud.h").read_text())[:36]
    glyphs = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", alphabet))
    glyphs.update({c: glyphs[c.upper()] for c in "abcdefghijklmnopqrstuvwxyz"})
    glyphs.update({"/": "00001/00001/00010/00100/01000/10000/10000",
                   "-": "00000/00000/00000/11111/00000/00000/00000",
                   ":": "00000/00100/00100/00000/00100/00100/00000",
                   "'": "00100/00100/00000/00000/00000/00000/00000",
                   ".": "00000/00000/00000/00000/00000/00000/00100"})
    font = bytearray(256 * 128 * 4)
    for code in range(33, 127):
        bits = glyphs.get(chr(code), "11111/10001/00010/00100/00100/00000/00100").split("/")
        ox, oy = ((code - 32) % 16) * 16, ((code - 32) // 16) * 20
        for y in range(10):
            for x in range(6):
                if bits[y * 7 // 10][x * 5 // 6] == "1":
                    at = ((oy + y) * 256 + ox + x) * 4
                    font[at:at + 4] = b"\xff" * 4
    # A 32x32 warding sigil: a circle and a five-pointed star in dull gold.
    sigil = bytearray(32 * 32 * 4)
    pts = [(16 + 13 * math.cos(-math.pi / 2 + k * 4 * math.pi / 5), 16 + 13 * math.sin(-math.pi / 2 + k * 4 * math.pi / 5)) for k in range(6)]
    for y in range(32):
        for x in range(32):
            d = math.hypot(x - 15.5, y - 15.5)
            on = 13.2 < d < 15
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                L = math.hypot(x1 - x0, y1 - y0)
                t = max(0, min(1, ((x - x0) * (x1 - x0) + (y - y0) * (y1 - y0)) / (L * L)))
                if math.hypot(x - (x0 + t * (x1 - x0)), y - (y0 + t * (y1 - y0))) < .9:
                    on = True
            if on:
                sigil[(y * 32 + x) * 4:(y * 32 + x) * 4 + 4] = bytes([190, 150, 60, 255])
    records = []

    def record(kind, rect, binding="", text="", anchor=(0, 0), color=0xFFFFFFFF, target=0, texture=0, uv=(0, 0, 1, 1)):
        records.append(u(kind) + f(anchor) + f(rect) + u(texture) + f(list(uv)) + string(binding)
                       + string(text) + u(color) + u(target) + u(0))

    def panel(rect, anchor=(0, 0), target=0, texture=1):
        record(0, rect, anchor=anchor, target=target, texture=texture)
    textures = [(256, 128, font), (1, 1, bytes([16, 12, 14, 232])), (1, 1, bytes([150, 18, 24, 255])),
                (1, 1, bytes([96, 50, 150, 255])), (1, 1, bytes([176, 136, 52, 255])),
                (1, 1, bytes([120, 92, 40, 255])), (32, 32, bytes(sigil)), (1, 1, bytes([46, 20, 26, 255]))]
    art = hud_art()
    if art is None:
        panel([12, 12, 300, 110])
        panel([14, 14, 298, 16], texture=5)
        panel([14, 106, 298, 108], texture=5)
        record(0, [20, 20, 52, 52], texture=6)
        panel([-160, 12, 160, 84], (0.5, 0), 1)
        record(0, [58, 50, 285, 66], "health", texture=2)
        record(0, [58, 76, 285, 92], "resource", texture=3)
        record(1, [58, 24, 285, 44], "player_name", color=0xFFE0C890)
        record(1, [64, 51, 280, 70], "health_text")
        record(1, [64, 77, 280, 96], "resource_text")
        record(1, [-145, 22, 145, 77], "target_name", anchor=(0.5, 0), target=1, color=0xFFE08070)
        panel([12, -178, 510, -80], (0, 1))
        panel([520, -178, 1014, -80], (0, 1))
        record(1, [24, -168, 495, -132], "chat", anchor=(0, 1))
        record(1, [24, -116, 495, -88], "chat_input", anchor=(0, 1))
        record(2, [12, -178, 510, -80], "chat", anchor=(0, 1))
        record(1, [532, -168, 1000, -85], "combat", anchor=(0, 1), color=0xFFE0C890)
        panel([12, -72, 1014, -12], (0, 1))
        panel([24, -62, 164, -24], (0, 1), texture=7)
        record(1, [34, -55, 155, -25], text="R / SPACE / 1\nHEX", anchor=(0, 1), color=0xFFE0C890)
        record(2, [24, -62, 164, -24], "strike", anchor=(0, 1))
        record(0, [185, -34, 625, -23], "xp", anchor=(0, 1), texture=4)
        record(1, [185, -59, 630, -38], "xp_text", anchor=(0, 1))
        record(1, [660, -59, 1000, -24], text="TAB TARGET / ENTER CHAT\nF LOOT / E RISE AGAIN / HOLD Q HASTE",
               anchor=(0, 1), color=0xFFB0A080)
    else:
        # Meshy-painted HUD art (nano-banana-pro): framed panels as 9-slices so
        # corners keep their pixels, a socketed action bar and an icon atlas.
        T = {}
        for name in ("frame", "bar", "icons", "leather"):
            T[name] = len(textures)
            textures.append(art[name])

        def nine(rect, name, border_tex, border, anchor=(0, 0), target=0):
            w, h, _ = art[name]
            x0, y0, x1, y1 = rect
            xs, ys = [x0, x0 + border, x1 - border, x1], [y0, y0 + border, y1 - border, y1]
            us = [0, border_tex / w, 1 - border_tex / w, 1]
            vs = [0, border_tex / h, 1 - border_tex / h, 1]
            for j in range(3):
                for i in range(3):
                    record(0, [xs[i], ys[j], xs[i + 1], ys[j + 1]], anchor=anchor, target=target,
                           texture=T[name], uv=(us[i], vs[j], us[i + 1], vs[j + 1]))

        def icon(index, rect, anchor=(0, 0)):
            c, r = index % 3, index // 3
            record(0, rect, anchor=anchor, texture=T["icons"], uv=(c / 3, r / 3, (c + 1) / 3, (r + 1) / 3))
        nine([4, 4, 336, 142], "frame", 95, 28)
        record(0, [34, 36, 62, 64], texture=6)
        record(1, [70, 36, 300, 54], "player_name", color=0xFFE0C890)
        record(0, [70, 64, 306, 80], "health", texture=2)
        record(1, [76, 65, 300, 82], "health_text")
        record(0, [70, 88, 306, 104], "resource", texture=3)
        record(1, [76, 89, 300, 106], "resource_text")
        nine([-170, 4, 170, 96], "frame", 95, 22, anchor=(0.5, 0), target=1)
        record(1, [-140, 30, 140, 80], "target_name", anchor=(0.5, 0), target=1, color=0xFFE08070)
        for x0, x1 in ((12, 510), (520, 1014)):
            record(0, [x0, -272, x1, -156], anchor=(0, 1), texture=T["leather"])
            panel([x0, -272, x1, -270], (0, 1), texture=5)
            panel([x0, -158, x1, -156], (0, 1), texture=5)
        record(1, [24, -262, 495, -226], "chat", anchor=(0, 1))
        record(1, [24, -206, 495, -170], "chat_input", anchor=(0, 1))
        record(2, [12, -272, 510, -156], "chat", anchor=(0, 1))
        record(1, [532, -262, 1000, -160], "combat", anchor=(0, 1), color=0xFFE0C890)
        record(0, [-250, -146, 250, -138], "xp", anchor=(0.5, 1), texture=4)
        record(1, [-250, -150, 250, -132], "xp_text", anchor=(0.5, 1))
        record(0, [-330, -126, 330, -6], anchor=(0.5, 1), texture=T["bar"])
        # Socket centres measured on the bar art: x = 0.178 + 0.0935 i, y = 0.55.
        for socket, index in enumerate([0, 1, 2, 3, 4, 5, 6, 8]):
            cx, cy = -330 + (.178 + .0935 * socket) * 660, -126 + .55 * 120
            rect = [cx - 20, cy - 20, cx + 20, cy + 20]
            icon(index, rect, anchor=(0.5, 1))
            if socket == 0:
                record(2, rect, "strike", anchor=(0.5, 1))
        record(1, [12, -60, 170, -20], text="R / SPACE / 1\nHEX", anchor=(0, 1), color=0xFFE0C890)
        record(1, [-420, 40, -12, 80], text="TAB TARGET / ENTER CHAT\nF LOOT / E RISE AGAIN / HOLD Q HASTE",
               anchor=(1, 0), color=0xFFB0A080)
    data = b"N3H1" + u(0) + f([60, 20]) + u(len(textures))
    for w, h, pixels in textures:
        data += u(w) + u(h) + bytes(pixels)
    (root / "hud.bin").write_bytes(data + u(len(records)) + b"".join(records))


# ---------------------------------------------------------------- package

def lod_bytes(world):
    xs = [v[0] for v in world.vertices]
    zs = [v[2] for v in world.vertices]
    ys = [v[1] for v in world.vertices]
    center = [(min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2]
    radius = max(math.dist(center, v[:3]) for v in world.vertices)
    return (b"N3L1" + u(1) + f(center) + f([radius, 1.0]) + u(0) + u(1) + f([0.0])
            + u(len(world.indices)) + b"".join(u(i) for i in world.indices))


def manifest(spawns, player_spawn, animation=None, npc="imp", scene_source="npc-idle.gltf"):
    m = json.loads(Path("games/demo/package.json").read_text())
    text = json.dumps(m).replace('"demo:', '"%s:' % GAME)
    m = json.loads(text)
    m.update(game_id=GAME, package_version="0.1.0", engine_version=13, protocol_version=7)
    m["assets"] = [{"id": GAME + ":creature/" + npc, "source": scene_source, "metadata": "scene.json", "dependencies": []}]
    g = m["gameplay"]
    g.update(action=GAME + ":action/hex", item=GAME + ":item/relic", npc=GAME + ":creature/" + npc,
             spawn_x=player_spawn[0], spawn_z=player_spawn[1], spawns=[list(s) for s in spawns],
             npc_health=50, npc_damage=6, aggro_range=5, leash_range=12, npc_speed=2.6, npc_range=.9,
             interest_cell=32)
    m["progression"].update(curve=GAME + ":curve/normal", item=GAME + ":item/relic",
                            origin="original synthetic", author="n3e ashgrave exploration", revision=1)
    m["world"] = GAME + ".n3world"
    m["exploration"] = {"turbo_multiplier": 6, "fog_start": 4.0, "fog_end": 50.0,
                        "fog_color": [0.05, 0.055, 0.075], "lod": "world-lod.bin"}
    m["editing"]["lighting"] = 0.45   # night: lit windows and lamps carry the light
    m["camera"]["distance"] = 6
    # The editable decoration: a small imp effigy on the memorial's upper plinth.
    m["editing"]["decorations"] = [{"id": "effigy", "position": [0.9, 1.2, 0.9], "yaw": 2.3, "scale": 1, "visual": "scene.bin"}]
    if animation is None:
        animation = [{"duration": d, "blend": .2, "loop_blend": False, "markers": mk}
                     for d, _, _, mk in investigator_clips() + imp_clips()]
    m["animation"] = animation
    return m


def generate():
    shutil.rmtree(SRC, ignore_errors=True)
    SRC.mkdir(parents=True)
    des_level = demons_souls_level() if __import__("os").environ.get("ASHGRAVE_WORLD") == "demons-souls" else None
    if des_level:
        (SRC / (GAME + ".n3world")).write_bytes(des_level["world"])
        (SRC / "world-lod.bin").write_bytes(des_level["lod"])
    else:
        world, heights = build_world()
        (SRC / (GAME + ".n3world")).write_bytes(
            b"N3W1" + u(ATLAS) + u(ATLAS) + u(CELL) + u(PAD) + atlas() + u(len(world.vertices))
            + b"".join(f(v) for v in world.vertices) + u(len(world.indices)) + b"".join(u(i) for i in world.indices))
        (SRC / "world-lod.bin").write_bytes(lod_bytes(world))
    variant = __import__("os").environ.get("ASHGRAVE_CHARACTERS", "procedural")
    kaykit = variant == "kaykit"
    if variant in ("meshy", "demons-souls"):
        player_animation = meshy_detective() if variant == "meshy" else demons_souls_player()
        animation, npc, scene_source, npc_scale = player_animation, "imp", "npc-idle.gltf", 1.0
        rig, pal = imp()
        (SRC / "imp.png").write_bytes(png_rgb(64, 64, pal.rgb()))
        npc_attachment = rig.index["fore_r"]
        for state, (duration, frames, pose, markers) in zip(["idle", "walk", "attack", "death"], imp_clips()):
            path = SRC / f"npc-{state}.gltf"
            write_gltf(path, rig, "imp.png", npc_attachment, clip(rig, duration, frames, pose), duration)
            cooked, _ = gltf.cook(SRC, path.name, {"instance_scale": [1, 1, 1], "attachment_node": npc_attachment})
            (SRC / f"npc-{state}.bin").write_bytes(cooked)
            animation.append({"duration": duration, "blend": .2, "loop_blend": False, "markers": markers})
    elif variant in ("refined", "mpfb", "synty"):
        # Blender-refined investigator on the same rig and clips; procedural imp.
        animation, npc, scene_source, npc_scale = None, "imp", "npc-idle.gltf", 1.0
        rig, texture_png = {"refined": refined_investigator, "mpfb": mpfb_investigator,
                            "synty": synty_investigator}[variant]()
        npc_attachment = rig.index["fore_r"]
        for prefix, (r, png, clips) in (("player", (rig, texture_png, investigator_clips())),
                                        ("npc", (*imp_png(), imp_clips()))):
            states = ["idle", "walk", "attack", "death", "run", "backward", "ready"][:len(clips)]
            for state, (duration, frames, pose, _) in zip(states, clips):
                path = SRC / f"{prefix}-{state}.gltf"
                write_gltf(path, r, png, r.index["fore_r"], clip(r, duration, frames, pose), duration)
                cooked, _ = gltf.cook(SRC, path.name, {"instance_scale": [1, 1, 1], "attachment_node": r.index["fore_r"]})
                (SRC / f"{prefix}-{state}.bin").write_bytes(cooked)
    elif kaykit:
        animation, npc_attachment, npc_scale = kaykit_characters()
        npc, scene_source = "revenant", "characters/npc-idle.gltf"
    else:
        animation, npc, scene_source, npc_scale = None, "imp", "npc-idle.gltf", 1.0
        for name, (rig, pal), clips, prefix in [("investigator", investigator(), investigator_clips(), "player"),
                                                ("imp", imp(), imp_clips(), "npc")]:
            (SRC / (name + ".png")).write_bytes(png_rgb(64, 64, pal.rgb()))
            states = ["idle", "walk", "attack", "death", "run", "backward", "ready"][:len(clips)]
            attachment = rig.index["fore_r"]
            npc_attachment = attachment
            for state, (duration, frames, pose, _) in zip(states, clips):
                path = SRC / f"{prefix}-{state}.gltf"
                write_gltf(path, rig, name + ".png", attachment, clip(rig, duration, frames, pose), duration)
                meta = {"instance_scale": [1, 1, 1], "attachment_node": attachment}
                cooked, _ = gltf.cook(SRC, path.name, meta)
                (SRC / f"{prefix}-{state}.bin").write_bytes(cooked)
    npc_strike = .45
    enemy = ENEMIES.get(__import__("os").environ.get("ASHGRAVE_NPC", ""))
    if enemy:
        # Keep the player's clips; the enemy's four always come last.
        animation = (animation[:-4] if animation is not None else
                     [{"duration": d, "blend": .2, "loop_blend": False, "markers": mk}
                      for d, _, _, mk in investigator_clips()])
        enemy_animation, npc_scale, npc_strike = enemy[0]()
        animation += enemy_animation
        npc, scene_source, npc_attachment = enemy[1], enemy[2], 0
    hud(SRC)
    spawns = [(26, 22), (40, 24), (24, 36), (41, 40), (35, 44)]
    player_spawn = (0, 8)
    if des_level:
        spawns, player_spawn = des_level["spawns"], des_level["player_spawn"]
        heightfield, collision = des_level["heightfield"], des_level["collision"]
    else:
        heightfield = {"width": SAMPLES, "depth": SAMPLES, "origin": [-HALF, 0, -HALF], "spacing": SPACING,
                       "heights": heights, "diagonal": "fixed"}
        collision = world.collision
    scene = {"instance_scale": [npc_scale] * 3, "attachment_node": npc_attachment, "heightfield": heightfield,
             "triangles": [collision[i:i + 3] for i in range(0, len(collision), 3)], "markers": [{"name": "claw", "time": npc_strike}]}
    (SRC / "scene.json").write_text(json.dumps(scene))
    m = manifest(spawns, player_spawn, animation, npc, scene_source)
    if variant == "demons-souls":
        # Pace the player's attacks to the 1.4 s sword clip as well.
        m["gameplay"]["cooldown_ticks"] = max(m["gameplay"]["cooldown_ticks"], math.ceil((animation[2]["duration"] + .2) * 20))
    if des_level:
        # Boletaria's grey overcast: daylight, long grey fog; the effigy stands by the start.
        m["exploration"].update(fog_start=15.0, fog_end=140.0, fog_color=[0.42, 0.44, 0.47])
        m["editing"]["lighting"] = 0.85
        m["editing"]["decorations"][0]["position"] = des_level["effigy"]
    if enemy:
        # Imported enemies bring long clips (the Demon's Souls attack is 2 s, its death
        # 2.9 s). Pace their attacks to the attack clip, and keep the corpse (life
        # policy) for a while after the death clip, so neither is cut short.
        attack, death = animation[-2]["duration"], animation[-1]["duration"]
        m["gameplay"]["npc_cooldown_ticks"] = max(m["gameplay"]["npc_cooldown_ticks"], math.ceil((attack + .2) * 20))
        life = m["life"]
        life["npc_corpse_ticks"] = max(life["npc_corpse_ticks"], math.ceil((death + 2.5) * 20))
        life["npc_respawn_ticks"] = max(life["npc_respawn_ticks"], life["npc_corpse_ticks"])
    m["presentation"] = {n: n for n in ["player-idle.bin", "player-walk.bin", "player-attack.bin",
                                         "player-death.bin", "player-run.bin", "player-backward.bin",
                                         "player-ready.bin", "npc-idle.bin", "npc-walk.bin", "npc-attack.bin",
                                         "npc-death.bin", "hud.bin"]}
    (SRC / "package.json").write_text(json.dumps(m, indent=2))
    characters = ("Characters: CC0 KayKit (Kay Lousberg, www.kaylousberg.com) through Blender 5.2.2:\n"
                  "KayKit-Character-Pack-Adventures-1.0 @ 672074b7 (Rogue_Hooded, recoloured) and\n"
                  "KayKit-Character-Pack-Skeletons-1.0 @ 15b62b9b (Skeleton_Minion), both CC0 1.0.\n") if kaykit else \
        ("Characters: investigator made with MPFB 2.0.17 (GPL add-on, not redistributed) and the CC0\n"
         "MakeHuman system assets (proxy741, middleage_caucasian_male skin, male_elegantsuit01, shoes01,\n"
         "short02, eyebrow001, low-poly eyes); content made with MPFB is CC0. Coat skirt, belt, bake and\n"
         "clips by the generator; imp box-modelled.\n") if variant == "mpfb" else \
        ("Characters: investigator from the Synty POLYGON Starter Pack v2 (base male and hair, Characters.fbx;\n"
         "PolygonStarter_Texture_01), free under Synty's One-Time Purchase Licence; source files are not\n"
         "redistributed. Arms lowered, faces moved onto palette swatches and bones mapped by the\n"
         "generator; clips scripted; imp box-modelled.\n") if variant == "synty" else \
        ("Characters: detective generated, textured, auto-rigged and animated by Meshy (meshy-6) on the\n"
         "user's Meshy Pro account (text-to-3d 01a0d9f3, refine 01a0d9f4, rig 01a0d9f6, animations\n"
         "01a0d9f7-*); used under Meshy's paid-plan terms. Imp box-modelled.\n") if variant == "meshy" else \
        "Characters: box-modelled and scripted by the generator.\n"
    (SRC / "PROVENANCE.md").write_text(
        "# Ashgrave provenance\n\nGenerated by `tools/assetc/ashgrave.py`. The world, textures and HUD are procedural\n"
        "(Python standard library); the HUD glyphs reuse the engine's bitmap alphabet\n"
        "(`client/render/hud.h`). No Knight Online assets.\n" + characters
        + ("Player: Demon's Souls player skeleton and clips (c0000) in armour 8100 with short sword wp_a_0200,\n"
           "from the user's own dump. Proprietary; local use only.\n" if variant == "demons-souls" else "")
        + ("World: Demon's Souls level 1-1, Gates of Boletaria (m02_00_00_00), cropped and simplified from the\n"
           "user's own dump (map pieces, textures and layout). Proprietary; local use only.\n" if des_level else "")
        + (enemy[3] + "Proprietary; local use only, never committed or distributed.\n" if enemy else ""))
    if not des_level:
        print("world vertices", len(world.vertices), "indices", len(world.indices),
              "collision triangles", len(world.collision) // 3)
    shutil.rmtree(OUT, ignore_errors=True)
    main.cook(SRC, OUT)
    print("cooked", OUT, (OUT / "release.sha256").read_text().strip())


if __name__ == "__main__":
    generate()
