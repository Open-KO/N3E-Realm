"""Original synthetic KO-format client tree for the PQ-254 importer checks.
Original n3e implementation; no KO data. The byte layouts are the ones
tools/assetc/ko_character.py reads (see tests/ko_character.py).

`write(root, rows)` writes a `Data/NPC_Looks.tbl.csv` with the 38-column
header and the given rows, and the files a check names: one-triangle parts
in solid red, green or blue (each 4 x 4 DXT1), a one-joint skeleton turning
over 30 keys (and variants: keys from 0.3 rad, no keys), clip tables
(eleven clips, five, two, one, none, held), a broken skeleton and two
.n3chr files."""
import math
import struct

from common import f, string

TYPES = ["UInt32"] + ["String"] * 16 + ["Int32"] * 18 + ["Byte"] * 3
# DXT1 endpoint colours (c0 > c1, every texel index 0 = c0).
COLORS = {"red": (0xF800, 0x07E0), "green": (0x07E0, 0x001F), "blue": (0x001F, 0x0000)}
RGB = {"red": bytes([255, 0, 0]), "green": bytes([0, 255, 0]), "blue": bytes([0, 0, 255])}


def ints(*v):
    return struct.pack("<" + "i" * len(v), *v)


def transform(name):
    # name, translation, rotation, scale, then no translation/rotation/scale keys
    return string(name) + f([0, 0, 0, 0, 0, 0, 1, 1, 1, 1]) + ints(0, 0, 0)


def joint(keys=30, start=0.0):
    """One root joint whose rotation turns about y over `keys` keys at 30 Hz,
    from `start` radians (key i at start + i / 100)."""
    quats = []
    for i in range(keys):
        a = start + i * 0.01
        quats += [0, math.sin(a), 0, math.cos(a)]
    return (string("root") + f([0, 0, 0, 0, 0, 0, 1, 1, 1, 1]) + ints(0) + ints(keys, 1) + f([30]) + f(quats)
            + ints(0, 0, 0))


def still_joint(angle=0.2):
    """One root joint without key tracks, turned `angle` radians about y
    (PQ-268: the crystals' and three guard stones' skeletons have no keys)."""
    return string("root") + f([0, 0, 0, 0, math.sin(angle), 0, math.cos(angle), 1, 1, 1]) + ints(0, 0, 0, 0, 0)


def animation(clips, held=()):
    """`clips` clips; clip i runs frames 0 .. 1 + i at 10 fps: (1 + i) / 10 s.
    A clip in `held` starts and ends on frame 2.5 instead, with its first
    strike frame there, as KO's shop and smith attack clips do (PQ-273)."""
    out = ints(clips)
    for i in range(clips):
        start, end, strike = (2.5, 2.5, 2.5) if i in held else (0, 1 + i, 0)
        out += ints(0) + f([start, end, 10, 0, 0, 0, 0, 0.2]) + ints(1 if i in (0, 1, 2) else 0) + f([strike, 0])
        out += string("clip%d" % i)
    return out


def texture(color):
    c0, c1 = COLORS[color]
    return string(color) + b"NTF\x03" + ints(4, 4, 0x31545844, 1) + struct.pack("<HHI", c0, c1, 0)


def skin(x):
    """One triangle at x .. x + 1 (four LODs, the last three empty)."""
    out = string("skins") + string("lod0") + ints(1, 3, 3)
    corners = ([x, 0, 0], [x + 1, 0, 0], [x, 1, 0])
    out += f([v for c in corners for v in c + [0, 0, 1]]) + struct.pack("<3H", 0, 1, 2)
    out += f([0, 0, 1, 0, 0, 1]) + struct.pack("<3H", 0, 1, 2)
    for c in corners:
        out += f(c) + ints(1, 0, 0, 0)
    return out + (string("empty") + ints(0, 0, 0)) * 3


def part(color, flags=0, texture_name=None):
    """A part with render flags `flags` (PQ-265: 1 blend, 4 cull
    off, 0x40 lighting off; blend factors 5/6) on `texture_name`."""
    material = f([1] * 4 + [0.5, 0.5, 0.5, 1] + [0] * 9) + struct.pack("<6I", 4, 0, 2, flags, 5, 6)
    return (string(color) + ints(0) + material + string("item/%s.dxt" % (texture_name or color))
            + string("item/%s.n3cskins" % color))


def see_through():
    """4 x 4 DXT1, red on the top two rows, transparent black (index 3 of a
    three-colour block) on the bottom two."""
    return string("wing") + b"NTF\x03" + ints(4, 4, 0x31545844, 1) + struct.pack("<HHI", 0xF800, 0xF800, 0xFFFF0000)


def glow():
    """4 x 4 DXT3, blue, alpha 8/15 on every texel."""
    return (string("glow") + b"NTF\x03" + ints(4, 4, 0x33545844, 1)
            + struct.pack("<QHHI", sum(8 << (4 * i) for i in range(16)), 0x001F, 0x0000, 0))


def character(joint_name, parts, animation_name, extras=("", "")):
    out = transform("synthetic") + string("") * 2 + string(joint_name) + ints(len(parts))
    out += b"".join(string(p) for p in parts) + ints(0) + string(animation_name) + ints(-1, -1, -1, -1)
    return out + b"".join(string(e) for e in extras)


def row(pid, **columns):
    """A 38-column looks row; `columns` maps 1-based column numbers (c3 ...)
    to values; strings default to '', integers to 0, column 35 to 1."""
    out = [str(pid), "synthetic"] + [""] * 15 + ["0"] * 18 + ["0", "100", "100"]
    out[34] = "1"
    for name, value in columns.items():
        out[int(name[1:]) - 1] = str(value)
    return out


def write(root, rows):
    """Writes the synthetic client tree under `root`."""
    files = {"chr/a.n3joint": joint(), "chr/a.n3anim": animation(11), "chr/short.n3anim": animation(5),
             "chr/none.n3anim": ints(0), "chr/held.n3anim": animation(11, held=range(4, 10)),
             "chr/broken.n3joint": joint()[:-3],
             # PQ-268: a table of one clip and one of two (KO's guard stones
             # 24000 and 14001), a skeleton whose keys start at 0.3 rad (its
             # frame-0 pose differs from its base rotation), one without keys,
             # and an .n3chr naming the clip table without clips.
             "chr/one.n3anim": animation(1), "chr/two.n3anim": animation(2),
             "chr/rest.n3joint": joint(start=0.3), "chr/still.n3joint": still_joint(),
             "chr/c.n3chr": character("chr/still.n3joint", ["item/blue.n3cpart"], "chr/none.n3anim"),
             "chr/b.n3chr": character("chr/a.n3joint", ["item/blue.n3cpart", "item/green.n3cpart"],
                                      "chr/a.n3anim", ("chr/b.n3fxplug", ""))}
    for i, color in enumerate(COLORS):
        files["item/%s.n3cpart" % color] = part(color)
        files["item/%s.n3cskins" % color] = skin(2 * i)
        files["item/%s.dxt" % color] = texture(color)
    # PQ-265: a double-sided part on a see-through texture and a blended,
    # unlit part on a DXT3 texture (their skins are the red and blue ones').
    files["item/wing.n3cpart"] = part("red", 4, "wing")
    files["item/wing.dxt"] = see_through()
    files["item/glow.n3cpart"] = part("blue", 0x41, "glow")
    files["item/glow.dxt"] = glow()
    for name, data in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(data)
    header = ",".join('"%d - %s"' % (i + 1, t) for i, t in enumerate(TYPES))
    body = "\n".join(",".join('"%s"' % v for v in r) for r in rows)
    (root / "Data").mkdir(parents=True, exist_ok=True)
    (root / "Data/NPC_Looks.tbl.csv").write_bytes(("﻿" + header + "\n" + body + "\n").encode("utf-8"))
