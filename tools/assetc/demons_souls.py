#!/usr/bin/env python3
"""Demon's Souls (PS3) characters from a player-supplied dump (exploration).

    python3 tools/assetc/demons_souls.py verify c2010
    python3 tools/assetc/demons_souls.py export c2010 idle=a00_0000,walk=a00_0200,attack=a00_3000 OUT_DIR
    python3 tools/assetc/demons_souls.py package c2010 idle=a00_0000,walk=a00_0200 OUT_DIR TEXTURE[,TEXTURE...]

The dump's `PS3_GAME/USRDIR` (only `chr/` is needed) is read from
`DES_USRDIR`, default `build/demons-souls/usrdir`. Nothing extracted is
committed. Formats follow JKAnderson's SoulsFormats layouts (FLVER0, TPF, BND3,
DCX); Havok animation is decoded by `havok.py`.

`export` writes a Blender-previewable glTF (one primitive per texture, all
clips as named animations); `package` writes `gltf.cook`-subset clips (one per
state, one primitive, the chosen textures packed into one 1024 atlas). The game's space is mirrored on X to glTF's
right-handed space.
"""
import json
import math
import os
import struct
import subprocess
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import havok  # noqa: E402

USRDIR = Path(os.environ.get("DES_USRDIR", "build/demons-souls/usrdir"))


# The user's Google Drive export of the dump (four zips), pinned by sha256.
ZIPS = {
    "719b8c50ee655aebe8edb4675759b83c6c9d39dc09866fa21e604e3baa0105c6": "001",
    "aae4e6a28fd471c07c21e1008eb35332c663d9ee65192bbe6eb60a91c7f5b8fe": "002",
    "2df923bbe4dd37327b48b8b641a76ec7705e5bf733d94640ec7929213ccb5b80": "003",
    "169f4f8eeb9307be79318ca2db4122cdf4f48904188a007f7c7681c377e94f1e": "004",
}


def ensure_usrdir(folders=("chr",)):
    """Extract `PS3_GAME/USRDIR/<folder>` once from the pinned zips (`DES_ZIPS` glob, default ~/Downloads)."""
    folders = [f for f in folders if not (USRDIR / f).is_dir()]
    if not folders:
        return
    import glob
    import hashlib
    import zipfile
    pattern = os.environ.get("DES_ZIPS", str(Path("~/Downloads").expanduser() / "Demon's Souls-*.zip"))
    found = {}
    for path in glob.glob(pattern):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 22), b""):
                h.update(block)
        if h.hexdigest() in ZIPS:
            found[h.hexdigest()] = path
    if set(found) != set(ZIPS):
        raise FileNotFoundError(f"{pattern}: need the four pinned Demon's Souls dump zips (or set DES_USRDIR)")
    root = USRDIR.parent
    for path in found.values():
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if any(f"/PS3_GAME/USRDIR/{f}/" in name for f in folders) or name.endswith("/PS3_GAME/PARAM.SFO"):
                    z.extract(name, root)
    dump = next(root.glob("*/PS3_GAME"))
    if b"BLES00932" not in (dump / "PARAM.SFO").read_bytes():
        raise ValueError("not the BLES00932 dump")
    if not USRDIR.exists():
        USRDIR.parent.mkdir(parents=True, exist_ok=True)
        USRDIR.symlink_to(dump.resolve() / "USRDIR")


# ---------------------------------------------------------------- containers

def dcx(data):
    """Inflate a DCX (DFLT) container; other data passes through."""
    if data[:4] != b"DCX\0":
        return data
    at = data.find(b"DCA\0")
    return zlib.decompress(data[at + struct.unpack_from(">I", data, at + 4)[0]:])


def bnd3(data):
    """[(id, name, bytes)] of a BND3 archive."""
    data = dcx(data)
    if data[:4] != b"BND3":
        raise ValueError("not a BND3 archive")
    fmt, big = data[0xC], data[0xD]
    e = ">" if big or fmt & 1 else "<"
    count = struct.unpack_from(e + "i", data, 0x10)[0]
    has_id, has_name, has_size = fmt & 2, fmt & 0xC, fmt & 0x20
    entry = 12 + 4 * bool(has_id) + 4 * bool(has_name) + 4 * bool(has_size)
    out = []
    for i in range(count):
        at = 0x20 + entry * i
        size, offset = struct.unpack_from(e + "iI", data, at + 4)
        q = at + 12
        fid = struct.unpack_from(e + "i", data, q)[0] if has_id else -1
        q += 4 if has_id else 0
        name = None
        if has_name:
            no = struct.unpack_from(e + "i", data, q)[0]
            name = data[no:data.index(b"\0", no)].decode("shift_jis", "replace")
        out.append((fid, name, data[offset:offset + size]))
    return out


# ---------------------------------------------------------------- FLVER0 / TPF

def flver(data):
    """Bones, materials and meshes (vertices, triangles) of a FLVER0 model."""
    if data[:6] != b"FLVER\0":
        raise ValueError("not a FLVER")
    e = ">" if data[6:8] == b"B\0" else "<"
    u = lambda fmt, off: struct.unpack_from(e + fmt, data, off)  # noqa: E731
    version, data_off, _, ndummy, nmat, nbone, nmesh, _ = u("8i", 8)
    idx16, utf16 = data[0x48] == 16, data[0x49]

    def text(off):
        if utf16:
            end = off
            while data[end:end + 2] != b"\0\0":
                end += 2
            return data[off:end].decode("utf-16-be" if e == ">" else "utf-16-le")
        return data[off:data.index(b"\0", off)].decode("shift_jis", "replace")
    at = 0x80 + 0x40 * ndummy
    materials = []
    for _ in range(nmat):
        name_o, _mtd, tex_o, lay_o, _, layhdr_o = u("6i", at)
        at += 0x20
        textures = {}
        for k in range(data[tex_o]):
            path_o, type_o = u("2i", tex_o + 0x10 + 0x10 * k)
            textures[text(type_o) if type_o > 0 else k] = Path(text(path_o).replace("\\", "/")).stem
        offs = [lay_o] if not layhdr_o else [u("i", layhdr_o + 0x10 + 4 * k)[0] for k in range(u("i", layhdr_o)[0])]
        layouts = []
        for lo in offs:
            count, size = u("2h", lo)
            layouts.append((size, [u("5i", lo + 0x10 + 0x14 * k)[1:4] for k in range(count)]))
        materials.append({"name": text(name_o), "textures": textures, "layouts": layouts})
    bones = []
    for _ in range(nbone):
        bones.append({"t": u("3f", at), "name": text(u("i", at + 12)[0]), "r": u("3f", at + 16), "parent": u("h", at + 28)[0],
                      "s": u("3f", at + 32)})
        at += 0x80
    meshes = []
    for _ in range(nmesh):
        dynamic, mat, _, unk03 = data[at:at + 4]
        nidx, nvert = u("2i", at + 4)
        default_bone = u("h", at + 12)[0]
        palette = u("28h", at + 14)
        _, idx_off, _, buf_off, vb1, _, _ = u("7i", at + 0x48)
        at += 0x64
        indices = u("%d%s" % (nidx, "H" if idx16 else "I"), data_off + idx_off)
        layout = 0
        if vb1:
            layout, _, buf_off = u("3i", u("2i", vb1)[1])
        size, members = materials[mat]["layouts"][layout]
        verts = []
        for v in range(nvert):
            o = data_off + buf_off + v * size
            vert = {"uv": (0.0, 0.0), "n": (0.0, 1.0, 0.0), "bi": (0, 0, 0, 0), "bw": (1.0, 0.0, 0.0, 0.0)}
            for off, typ, sem in members:
                p = o + off
                if sem == 0:
                    vert["p"] = u("3f", p)
                elif sem == 3 and typ in (0x10, 0x11, 0x13, 0x2F):
                    vert["n"] = tuple((b - 127) / 127 for b in data[p:p + 3])
                elif sem == 3 and typ == 0x1A:
                    vert["n"] = tuple(x / 32767 for x in u("3h", p))
                elif sem == 5 and vert["uv"] == (0.0, 0.0) and typ in (0x10, 0x11, 0x12, 0x13, 0x15, 0x16):
                    vert["uv"] = tuple(x / 1024 for x in u("2h", p))
                elif sem == 2:
                    vert["bi"] = tuple(data[p:p + 4]) if typ in (0x11, 0x2F) else u("4H", p)
                elif sem == 1:
                    vert["bw"] = (tuple(b / 127 for b in struct.unpack_from("4b", data, p)) if typ == 0x10 else
                                  tuple(b / 255 for b in data[p:p + 4]) if typ == 0x13 else tuple(x / 32767 for x in u("4h", p)))
            verts.append(vert)
        if version >= 0x15 and unk03 == 0:
            tris = [tuple(indices[k:k + 3]) for k in range(0, len(indices), 3)]
        else:                                                   # strips with 0xFFFF restarts
            tris, flip = [], False
            for k in range(len(indices) - 2):
                a, b, c = indices[k:k + 3]
                if 0xFFFF in (a, b, c):
                    flip = False
                    continue
                if len({a, b, c}) == 3:
                    tris.append((c, b, a) if flip else (a, b, c))
                flip = not flip
        meshes.append({"material": mat, "dynamic": dynamic, "palette": palette, "default_bone": default_bone,
                       "verts": verts, "tris": tris})
    return {"bones": bones, "materials": materials, "meshes": meshes}


def bone_worlds(bones):
    """FLVER bone world matrices: T * Ry * Rz * Rx * S (SoulsFormats' local transform), parent first."""
    out = []
    for b in bones:
        rx, ry, rz = b["r"]
        cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
        X = [[1, 0, 0], [0, cx, -sx], [0, sx, cx]]
        Y = [[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]]
        Z = [[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]
        mm = lambda a, b: [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]  # noqa: E731
        r = mm(Y, mm(Z, X))
        m = [[r[i][0] * b["s"][0], r[i][1] * b["s"][1], r[i][2] * b["s"][2], b["t"][i]] for i in range(3)] + [[0, 0, 0, 1]]
        out.append(m if b["parent"] < 0 else _mul(out[b["parent"]], m))
    return out


FOURCC = {0: b"DXT1", 1: b"DXT1", 3: b"DXT3", 5: b"DXT5", 24: b"DXT1", 25: b"DXT1", 33: b"DXT5"}


def tpf(data):
    """{name: (format, width, height, bytes)} of a PS3 TPF."""
    if data[:4] != b"TPF\0":
        raise ValueError("not a TPF")
    e = ">" if data[0xC] in (2, 3) else "<"
    count = struct.unpack_from(e + "i", data, 8)[0]
    flag2, enc = data[0xD], data[0xE]
    at, out = 0x10, {}
    for _ in range(count):
        off, size = struct.unpack_from(e + "Ii", data, at)
        fmt = data[at + 8]
        w, h = struct.unpack_from(e + "2h", data, at + 12)
        at += 20 + (4 if flag2 else 0)
        name_o = struct.unpack_from(e + "I", data, at)[0]
        at += 8
        end = name_o
        if enc == 1:
            while data[end:end + 2] != b"\0\0":
                end += 2
        name = (data[name_o:end].decode("utf-16-be") if enc == 1 else
                data[name_o:data.index(b"\0", name_o)].decode("shift_jis", "replace"))
        out[name] = (fmt, w, h, data[off:off + size])
    return out


def texture_png(tex, png):
    """Wrap raw DXT data in a DDS header and decode it to RGB8 PNG with ImageMagick."""
    fmt, w, h, raw = tex
    fourcc = FOURCC.get(fmt)
    if not fourcc:
        raise ValueError(f"texture format {fmt}")
    top = max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * (8 if fourcc == b"DXT1" else 16)
    header = (struct.pack("<4s7I44x", b"DDS ", 124, 0x81007, h, w, top, 0, 1)
              + struct.pack("<2I4s5I", 32, 4, fourcc, 0, 0, 0, 0, 0) + struct.pack("<5I", 0x1000, 0, 0, 0, 0))
    dds = Path(str(png) + ".dds")
    dds.write_bytes(header + raw[:top])
    subprocess.run(["magick", str(dds), "-alpha", "off", "-define", "png:exclude-chunks=all", "PNG24:" + str(png)], check=True)
    dds.unlink()


# ---------------------------------------------------------------- characters

def animations(char):
    """{clip name: packfile} of a character's animation archive, plus its skeleton packfile."""
    folder = USRDIR / "chr" / char
    files = []
    for src in sorted(folder.glob(f"{char}*.anibnd")):          # the player splits clips across a0x..a4x
        files += bnd3(src.read_bytes())
    if not files:
        files = bnd3((folder / f"{char}.anibnd.dcx").read_bytes())
    clips, skel = {}, None
    for _, name, data in files:
        if not name or not name.lower().endswith(".hkx"):
            continue
        stem = Path(name.replace("\\", "/")).stem
        if stem.lower() == "skeleton":
            skel = havok.Packfile(data)
        elif havok.WAVELET.encode() in data:
            clips[stem] = havok.Packfile(data)
    return clips, skel


def _q(q):
    x, y, z, w = q
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]


def _mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _trs(t, q, s):
    r = _q(q)
    return [[r[i][0] * s[0], r[i][1] * s[1], r[i][2] * s[2], t[i]] for i in range(3)] + [[0, 0, 0, 1]]


def _mirror(m):
    """X mirror (game space -> right-handed glTF): M m M with M = diag(-1, 1, 1)."""
    sign = (-1, 1, 1, 1)
    return [[m[i][j] * sign[i] * sign[j] for j in range(4)] for i in range(4)]


def _invert(m):
    r = [[m[j][i] for j in range(3)] for i in range(3)]
    s2 = [sum(r[i][k] ** 2 for k in range(3)) for i in range(3)]
    r = [[r[i][k] / s2[i] for k in range(3)] for i in range(3)]
    t = [-sum(r[i][k] * m[k][3] for k in range(3)) for i in range(3)]
    return [r[i] + [t[i]] for i in range(3)] + [[0, 0, 0, 1]]


def part_models(names):
    """(FLVER, textures, attach bone) of each equipment part archive in `parts/`.

    A name is "bd_m_8000", or "wp_a_0200@R_Weapon" for a rigid part carried by a bone.
    """
    out = []
    for name in names:
        name, _, attach = name.partition("@")
        files = bnd3((USRDIR / "parts" / f"{name}.partsbnd").read_bytes())
        model = next(flver(data) for _, n, data in files if n and n.lower().endswith(".flver"))
        texs = {}
        for _, n, data in files:
            if n and n.lower().endswith(".tpf"):
                texs.update(tpf(data))
        out.append((model, texs, attach or None))
    return out


def character(char, textures=None, parts=None, skin_joints=None):
    """Skeleton, bind-pose world matrices and the X-mirrored, skinned mesh grouped by diffuse texture.

    The mesh is the character's own FLVER, or the given equipment parts skinned to its skeleton.
    """
    anims, skel = animations(char)
    names, parents, pose = havok.skeleton(skel)
    world = []
    for i, p in enumerate(pose):
        m = _trs(*p)
        world.append(m if parents[i] < 0 else _mul(world[parents[i]], m))
    folder = USRDIR / "chr" / char
    models = part_models(parts) if parts else [(flver((folder / f"{char}.flver").read_bytes()),
                                                 tpf((folder / f"{char}.tpf").read_bytes()), None)]
    c = {"anims": anims, "names": names, "parents": parents, "pose": pose, "world": world, "textures": {},
         "pos": [], "nrm": [], "uv": [], "jnt": [], "wgt": [], "groups": {}}
    # Node order: finger bones last, so the rest of a large skeleton fits 64-bit node masks.
    order = [i for i, n in enumerate(names) if "Finger" not in n] + [i for i, n in enumerate(names) if "Finger" in n]
    c["node_of"] = {j: i for i, j in enumerate(order)}
    c["order"] = order
    if parts and (USRDIR / "parts" / "common_body.tpf").exists():        # bare skin and faces under armour
        c["textures"].update(tpf((USRDIR / "parts" / "common_body.tpf").read_bytes()))
    for model, texs, attach in models:
        c["textures"].update(texs)
        _add_model(c, model, textures, attach)
    # Skin joints: only bones that carry weight (the engine allows 64), or a list shared
    # with other meshes (render detail); JOINTS_0 index this list.
    used = sorted(skin_joints) if skin_joints else weighted_joints(c)
    missing = weighted_joints(c)
    if not set(missing) <= set(used):
        raise ValueError("skin joint list misses weighted bones")
    if len(used) < len(names):
        position = {j: i for i, j in enumerate(used)}
        c["skin_joints"] = used
        c["skin_jnt"] = [[position[j] if x > 0 else 0 for j, x in zip(js, ws)] for js, ws in zip(c["jnt"], c["wgt"])]
    return c


def weighted_joints(c):
    """Sorted skeleton indices that carry vertex weight, plus the root."""
    return sorted({0} | {j for js, ws in zip(c["jnt"], c["wgt"]) for j, x in zip(js, ws) if x > 0})


def _add_model(c, model, textures, attach=None):
    names, world = c["names"], c["world"]
    joint_of = {i: names.index(b["name"]) for i, b in enumerate(model["bones"]) if b["name"] in names}
    if attach:                          # a rigid part (weapon): every bone rides the carrying bone
        joint_of = {i: names.index(attach) for i in range(len(model["bones"]))}
    for mesh in model["meshes"]:
        diffuse = model["materials"][mesh["material"]]["textures"].get("g_Diffuse")
        if textures and diffuse not in textures:
            continue
        base = len(c["pos"])
        for v in mesh["verts"]:
            p = list(v["p"])
            if mesh["dynamic"]:
                joints = [joint_of.get(mesh["palette"][b], 0) if b < 28 else 0 for b in v["bi"]]
                weights = list(v["bw"])
            else:
                joints, weights = [joint_of.get(mesh["default_bone"], 0), 0, 0, 0], [1, 0, 0, 0]
                w = world[joints[0]]
                p = [sum(w[i][k] * p[k] for k in range(3)) + w[i][3] for i in range(3)]
            total = sum(weights) or 1
            n = v["n"]
            length = math.sqrt(sum(x * x for x in n)) or 1
            c["pos"].append([-p[0], p[1], p[2]])
            c["nrm"].append([-n[0] / length, n[1] / length, n[2] / length])
            c["uv"].append(list(v["uv"]))
            c["jnt"].append(joints)
            c["wgt"].append([x / total for x in weights])
        group = c["groups"].setdefault(diffuse, [])
        for tri in mesh["tris"]:
            group.append(_outward(c["pos"], c["nrm"], [base + k for k in tri]))


def _outward(pos, nrm, tri):
    """Order a triangle counter-clockwise about its vertex normals (glTF front faces)."""
    a, b, c = (pos[k] for k in tri)
    e1, e2 = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
    face = [e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]]
    if sum(face[i] * sum(nrm[k][i] for k in tri) for i in range(3)) < 0:
        return [tri[0], tri[2], tri[1]]
    return tri


def clip_tracks(c, clip):
    """Decoded clip as glTF keys: (times, {bone: (translations, rotations)}, strike time at peak joint motion)."""
    p = c["anims"][clip]
    bones = havok.binding(p)
    a = havok.wavelet_animation(p)
    n = a["frames"]
    times = [k * a["duration"] / (n - 1) for k in range(n)]
    keys, motion = {}, [0.0] * n
    for ti, track in enumerate(a["tracks"]):
        rot = []
        for k, q in enumerate(track["rot"]):
            length = math.sqrt(sum(x * x for x in q)) or 1
            q = [q[0] / length, -q[1] / length, -q[2] / length, q[3] / length]
            if rot and sum(x * y for x, y in zip(q, rot[-1])) < 0:
                q = [-x for x in q]
            if rot:
                motion[k] += 1 - abs(sum(x * y for x, y in zip(q, rot[-1])))
            rot.append(q)
        keys[c["node_of"][bones[ti]]] = ([[-v[0], v[1], v[2]] for v in track["pos"]], rot)
    return times, keys, times[max(range(n), key=lambda k: motion[k])]


class _Writer:
    def __init__(self):
        self.blob, self.views, self.accessors = bytearray(), [], []

    def add(self, fmt, values, kind, component, count, **extra):
        while len(self.blob) % 4:
            self.blob.append(0)
        data = struct.pack("<%d%s" % (len(values), fmt), *values)
        self.views.append({"buffer": 0, "byteOffset": len(self.blob), "byteLength": len(data)})
        self.blob.extend(data)
        self.accessors.append({"bufferView": len(self.views) - 1, "componentType": component, "count": count,
                               "type": kind, **extra})
        return len(self.accessors) - 1

    def animation(self, times, keys):
        a_t = self.add("f", times, "SCALAR", 5126, len(times), min=[0.0], max=[times[-1]])
        samplers, channels = [], []
        for bone, (trans, rot) in keys.items():
            for path, values in (("translation", trans), ("rotation", rot)):
                samplers.append({"input": a_t, "interpolation": "LINEAR",
                                 "output": self.add("f", _flat(values), "VEC4" if path == "rotation" else "VEC3",
                                                    5126, len(values))})
                channels.append({"sampler": len(samplers) - 1, "target": {"node": bone, "path": path}})
        return {"samplers": samplers, "channels": channels}

    def write(self, path, doc):
        doc.update(buffers=[{"uri": path.stem + ".bin", "byteLength": len(self.blob)}], bufferViews=self.views,
                   accessors=self.accessors)
        path.with_suffix(".bin").write_bytes(bytes(self.blob))
        path.write_text(json.dumps(doc))


def _flat(rows):
    return [v for r in rows for v in r]


def _skinned(c, w, uv, primitives, materials, images, animations):
    attributes = {"POSITION": w.add("f", _flat(c["pos"]), "VEC3", 5126, len(c["pos"]),
                                    min=[min(p[k] for p in c["pos"]) for k in range(3)],
                                    max=[max(p[k] for p in c["pos"]) for k in range(3)]),
                  "NORMAL": w.add("f", _flat(c["nrm"]), "VEC3", 5126, len(c["nrm"])),
                  "TEXCOORD_0": w.add("f", _flat(uv), "VEC2", 5126, len(uv)),
                  "JOINTS_0": w.add("H", _flat(c.get("skin_jnt") or c["jnt"]), "VEC4", 5123, len(c["jnt"])),
                  "WEIGHTS_0": w.add("f", _flat(c["wgt"]), "VEC4", 5126, len(c["wgt"]))}
    for prim in primitives:
        prim["attributes"] = attributes
    ibm = [_invert(_mirror(m)) for m in c["world"]]
    skin = c.get("skin_joints") or list(range(len(c["names"])))
    node_of = c["node_of"]
    nodes = []
    for i in c["order"]:
        t, q, s = c["pose"][i]
        length = math.sqrt(sum(x * x for x in q))
        node = {"name": c["names"][i], "translation": [-t[0], t[1], t[2]],
                "rotation": [q[0] / length, -q[1] / length, -q[2] / length, q[3] / length]}
        if any(abs(x - 1) > 1e-5 for x in s):
            # Some unweighted leaf "Nub" bones carry a mirrored (-1) scale from the authoring tool.
            node["scale"] = [abs(x) for x in s]
        children = [node_of[k] for k, p in enumerate(c["parents"]) if p == i]
        if children:
            node["children"] = children
        nodes.append(node)
    nodes.append({"name": "mesh", "mesh": 0, "skin": 0})
    doc = {"asset": {"version": "2.0", "generator": "n3e demons_souls.py (local extraction)"}, "scene": 0,
           "scenes": [{"nodes": [node_of[i] for i, p in enumerate(c["parents"]) if p < 0] + [len(nodes) - 1]}],
           "nodes": nodes, "meshes": [{"primitives": primitives}], "materials": materials, "images": images,
           "textures": [{"source": i} for i in range(len(images))],
           "skins": [{"joints": [node_of[j] for j in skin],
                      "inverseBindMatrices": w.add("f", [ibm[j][r][k] for j in skin for k in range(4) for r in range(4)],
                                                   "MAT4", 5126, len(skin))}]}
    if animations:
        doc["animations"] = animations
    return doc


def export(char, clips, out, textures=None, parts=None):
    """Blender-previewable glTF: one primitive per texture, every clip {label: clip name} as a named animation."""
    out.mkdir(parents=True, exist_ok=True)
    c = character(char, textures, parts)
    w = _Writer()
    materials, images, primitives = [], [], []
    for diffuse, tris in c["groups"].items():
        material = {"pbrMetallicRoughness": {"metallicFactor": 0}}
        if diffuse in c["textures"]:
            texture_png(c["textures"][diffuse], out / f"{diffuse}.png")
            images.append({"uri": f"{diffuse}.png"})
            material["pbrMetallicRoughness"]["baseColorTexture"] = {"index": len(images) - 1}
        materials.append(material)
        primitives.append({"material": len(materials) - 1, "indices": w.add("I", _flat(tris), "SCALAR", 5125, 3 * len(tris))})
    animations = []
    for label, clip in clips.items():
        times, keys, _ = clip_tracks(c, clip)
        animations.append({"name": label, **w.animation(times, keys)})
    w.write(out / f"{char}.gltf", _skinned(c, w, c["uv"], primitives, materials, images, animations))
    return len(c["pos"]), sum(len(t) for t in c["groups"].values())


def atlas(c, png, size=1024):
    """Shelf-pack the diffuse textures into one RGB8 atlas at the largest common scale that fits.

    Returns {texture: (x, y, w, h)} in pixels; textures missing from the TPFs get no place.
    """
    names = [t for t in c["groups"] if t in c["textures"]]
    for scale in (1, .75, .5, .375, .25, .125, .0625, .03125, .015625):
        dims = {t: (max(1, int(c["textures"][t][1] * scale)), max(1, int(c["textures"][t][2] * scale))) for t in names}
        place, x, y, shelf = {}, 0, 0, 0
        for t in sorted(names, key=lambda t: (-dims[t][1], -dims[t][0])):
            w, h = dims[t]
            if x + w > size:
                x, y, shelf = 0, y + shelf, 0
            place[t] = (x, y, w, h)
            x, shelf = x + w, max(shelf, h)
        if names and y + shelf <= size and all(w <= size for w, _ in dims.values()):
            break
    else:
        raise ValueError("atlas overflow")
    tmp = Path(str(png) + ".d")
    tmp.mkdir(exist_ok=True)
    # An explicit sRGB colour: a named "gray" canvas makes ImageMagick write a grayscale image.
    cmd = ["magick", "-size", f"{size}x{size}", "xc:srgb(128,128,128)"]
    for t, (px, py, pw, ph) in place.items():
        texture_png(c["textures"][t], tmp / f"{t}.png")
        cmd += ["(", str(tmp / f"{t}.png"), "-resize", f"{pw}x{ph}!", ")", "-geometry", f"+{px}+{py}", "-composite"]
    subprocess.run(cmd + ["-alpha", "off", "-type", "TrueColor", "-define", "png:exclude-chunks=all", "PNG24:" + str(png)],
                   check=True)
    for f in tmp.iterdir():
        f.unlink()
    tmp.rmdir()
    return place


def package(char, clips, out, textures=None, prefix="npc", size=1024, parts=None, skin_joints=None):
    """`gltf.cook`-subset clips: one glTF per state with one primitive, one atlas texture and one animation.

    Returns ({state: (duration, strike time)}, triangles, height in metres).
    """
    out.mkdir(parents=True, exist_ok=True)
    c = character(char, textures, parts, skin_joints)
    texture = f"{prefix}-texture.png"
    place = atlas(c, out / texture, size)
    corner_of = {}
    for diffuse, tris in c["groups"].items():
        for tri in tris:
            for k in tri:
                corner_of[k] = diffuse
    uv = []
    for k, (u, v) in enumerate(c["uv"]):
        x, y, w, h = place.get(corner_of.get(k), (size - 1, size - 1, 0, 0))   # unknown texture: gray corner
        uv.append([(x + min(max(u, 0), 1) * w) / size, (y + min(max(v, 0), 1) * h) / size])
    tris = [i for group in c["groups"].values() for tri in group for i in tri]
    results = {}
    for state, clip in clips.items():
        w = _Writer()
        primitives = [{"material": 0, "indices": w.add("I", tris, "SCALAR", 5125, len(tris))}]
        times, keys, strike = clip_tracks(c, clip)
        doc = _skinned(c, w, uv, primitives, [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
                       [{"uri": texture}], [w.animation(times, keys)])
        w.write(out / f"{prefix}-{state}.gltf", doc)
        results[state] = (round(times[-1], 6), round(strike, 4))
    heights = [p[1] for p in c["pos"]]
    return results, len(tris) // 3, max(heights) - min(heights)



# ---------------------------------------------------------------- levels

def msb_parts(data):
    """Parts of a Demon's Souls MSB (MSBD, big-endian): name, type, model, position, rotation (degrees), scale.

    Types: 0 map piece, 1 object, 2 enemy, 4 player start, 5 collision.
    """
    def params():
        at, out = 0, {}
        while True:
            name_o, count = struct.unpack_from(">ii", data, at + 4)
            offsets = struct.unpack_from(">%di" % (count - 1), data, at + 12)
            nxt = struct.unpack_from(">i", data, at + 12 + 4 * (count - 1))[0]
            out[data[name_o:data.index(b"\0", name_o)].decode()] = offsets
            if not nxt:
                return out
            at = nxt

    def text(o):
        return data[o:data.index(b"\0", o)].decode("shift_jis", "replace")
    ps = params()
    models = [text(o + struct.unpack_from(">i", data, o)[0]) for o in ps["MODEL_PARAM_ST"]]
    parts = []
    for o in ps["PARTS_PARAM_ST"]:
        name_o, kind, _, model = struct.unpack_from(">iIii", data, o)
        parts.append({"name": text(o + name_o), "type": kind, "model": models[model],
                      "pos": struct.unpack_from(">3f", data, o + 20), "rot": struct.unpack_from(">3f", data, o + 32),
                      "scale": struct.unpack_from(">3f", data, o + 44)})
    return parts


def texture_rgba(tex, size):
    """A TPF texture resampled to size x size RGBA bytes (DXT1/3/5 through ImageMagick, PS3 swizzled ARGB8 here)."""
    fmt, w, h, raw = tex
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "t.png"
        if fmt == 10:                                  # PS3 swizzled A8R8G8B8 (Morton order)
            px = bytearray(w * h * 4)
            x = y = 0
            for i in range(w * h):
                a, r, g, b = raw[4 * i:4 * i + 4]
                o = 4 * (y * w + x)
                px[o:o + 4] = bytes((r, g, b, a))
                xinc = (x & y) ^ ((x & y) + 1)
                yinc = x & xinc
                x ^= xinc
                y ^= yinc
            (Path(tmp) / "t.rgba").write_bytes(bytes(px))
            subprocess.run(["magick", "-size", f"{w}x{h}", "-depth", "8", f"RGBA:{tmp}/t.rgba", str(src)], check=True)
        else:
            fourcc = FOURCC.get(fmt)
            if not fourcc:
                raise ValueError(f"texture format {fmt}")
            top = max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * (8 if fourcc == b"DXT1" else 16)
            header = (struct.pack("<4s7I44x", b"DDS ", 124, 0x81007, h, w, top, 0, 1)
                      + struct.pack("<2I4s5I", 32, 4, fourcc, 0, 0, 0, 0, 0) + struct.pack("<5I", 0x1000, 0, 0, 0, 0))
            (Path(tmp) / "t.dds").write_bytes(header + raw[:top])
            src = Path(tmp) / "t.dds"
        return subprocess.run(["magick", str(src), "-resize", f"{size}x{size}!", "-depth", "8", "RGBA:-"],
                              check=True, capture_output=True).stdout


def level(map_id, box, limit=196000, collision_limit=64000, cell=256, pad=8, atlas_size=2048):
    """A cropped Demon's Souls level as an N3W1 world, collision triangles and placements.

    box = (x0, x1, z0, z1) in game coordinates; triangles are kept by centroid. The
    game's space is mirrored on X like the characters and recentred on the box.
    Geometry is simplified by vertex clustering, choosing the finest grid that fits
    `limit` triangles and vertices; collision uses a coarser grid.
    """
    ensure_usrdir(("map",))
    root = USRDIR / "map"
    parts = msb_parts((root / "mapstudio" / f"{map_id}.msb").read_bytes())
    area = map_id[:3]
    catalog = {}
    for tpf_path in sorted(list(root.glob(f"{area}/*.tpf")) + list(root.glob(f"{map_id}/*.tpf"))):
        for name, tex in tpf(tpf_path.read_bytes()).items():
            catalog.setdefault(name, tex)
    x0, x1, z0, z1 = box
    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
    tris = []          # (texture, [(pos, normal, uv)] * 3), recentred and mirrored
    for part in (p for p in parts if p["type"] == 0):
        path = root / map_id / (part["model"].lower() + ".flver")
        if not path.exists():
            path = Path(str(path) + ".dcx")
        model = flver(dcx(path.read_bytes()))
        bones = bone_worlds(model["bones"])
        place = bone_worlds([{"t": part["pos"], "r": [math.radians(v) for v in part["rot"]], "s": part["scale"], "parent": -1}])[0]
        for mesh in model["meshes"]:
            w = _mul(place, bones[mesh["default_bone"]]) if not mesh["dynamic"] and mesh["default_bone"] >= 0 else place
            texture = model["materials"][mesh["material"]]["textures"].get("g_Diffuse")
            verts = []
            for v in mesh["verts"]:
                p = [sum(w[i][k] * v["p"][k] for k in range(3)) + w[i][3] for i in range(3)]
                n = [sum(w[i][k] * v["n"][k] for k in range(3)) for i in range(3)]
                length = math.sqrt(sum(x * x for x in n)) or 1
                verts.append(((-(p[0] - cx), p[1], p[2] - cz), (-n[0] / length, n[1] / length, n[2] / length), v["uv"]))
            for a, b, c in mesh["tris"]:
                mx = -(verts[a][0][0] + verts[b][0][0] + verts[c][0][0]) / 3 + cx
                mz = (verts[a][0][2] + verts[b][0][2] + verts[c][0][2]) / 3 + cz
                if x0 <= mx <= x1 and z0 <= mz <= z1:
                    tris.append((texture, [verts[a], verts[b], verts[c]]))
    # Atlas: slot 0 is black (the additive second layer and missing textures), then by use.
    usage = {}
    for texture, _ in tris:
        usage[texture] = usage.get(texture, 0) + 1
    per_row = atlas_size // cell
    known = sorted((t for t in usage if t in catalog), key=lambda t: -usage[t])[:per_row * per_row - 1]
    slot_of = {t: i + 1 for i, t in enumerate(known)}
    inner = cell - 2 * pad
    atlas = bytearray(atlas_size * atlas_size * 4)
    for t, slot in slot_of.items():
        img = texture_rgba(catalog[t], inner)
        ox, oy = (slot % per_row) * cell, (slot // per_row) * cell
        for y in range(cell):                      # the pad repeats the wrapped opposite edge
            src = img[4 * inner * ((y - pad) % inner):4 * inner * ((y - pad) % inner + 1)]
            at = 4 * ((oy + y) * atlas_size + ox)
            atlas[at:at + 4 * cell] = src[-4 * pad:] + src + src[:4 * pad]

    def simplify(grid, want_uv):
        index, vertices, indices, rep = {}, [], [], {}
        for texture, corners in tris:
            keys = [tuple(round(c / grid) for c in pos) for pos, _, _ in corners]
            if len(set(keys)) < 3:
                continue
            tri = []
            for key, (pos, nrm, uv) in zip(keys, corners):
                pos = rep.setdefault(key, pos)
                # Merge render vertices on position, slot and UV to ~1/64 texel of a
                # 256 slot; normals are taken from the first corner (flat-ish detail).
                vk = (key, slot_of.get(texture, 0), round(uv[0] * 64), round(uv[1] * 64)) if want_uv else key
                if vk not in index:
                    index[vk] = len(vertices)
                    vertices.append((pos, nrm, uv, slot_of.get(texture, 0)))
                tri.append(index[vk])
            indices.append(tri)
        return vertices, indices

    for grid in (0.03, 0.05, 0.08, 0.1, 0.15, 0.2, 0.3, 0.4):
        vertices, indices = simplify(grid, True)
        print(f"level grid {grid} m: {len(indices)} triangles, {len(vertices)} vertices", file=sys.stderr)
        if len(indices) <= limit and len(vertices) <= limit:
            break
    else:
        raise ValueError("level crop too large for the world budget")
    positions, normals = [v[0] for v in vertices], [v[1] for v in vertices]
    oriented = [_outward(positions, normals, tri) for tri in indices]
    world = bytearray(b"N3W1" + struct.pack("<4I", atlas_size, atlas_size, cell, pad) + bytes(atlas)
                      + struct.pack("<I", len(vertices)))
    for pos, nrm, uv, slot in vertices:
        world += struct.pack("<12f", *pos, *nrm, uv[0], uv[1], 0.0, 0.0, float(slot), 0.0)
    world += struct.pack("<I", 3 * len(oriented)) + struct.pack("<%dI" % (3 * len(oriented)), *[k for t in oriented for k in t])
    # Collision: coarser, solid materials only (alpha-tested foliage and cloth are skipped).
    solid = {t for t in slot_of if FOURCC.get(catalog[t][0]) != b"DXT5"}
    render_grid = grid
    # Collision: the game's own collision meshes (Havok hkpStorageExtendedMeshShape in the
    # map's collision parts), cropped like the visuals; clustered visuals are only a fallback.
    collision = []
    for part in (p for p in parts if p["type"] == 5):
        path = root / map_id / (part["model"].lower() + ".hkx")
        if not path.exists():
            path = Path(str(path) + ".dcx")
        if not path.exists():
            continue
        place = bone_worlds([{"t": part["pos"], "r": [math.radians(v) for v in part["rot"]], "s": part["scale"], "parent": -1}])[0]
        pack = havok.Packfile(dcx(path.read_bytes()))
        for loc in pack.find("hkpStorageExtendedMeshShapeMeshSubpartStorage"):
            vloc, nv = pack.ptr(loc, 8), pack.unpack("i", loc, 12)[0]
            iloc, ni = pack.ptr(loc, 20), pack.unpack("i", loc, 24)[0]
            if not vloc or not iloc:
                continue
            raw = [pack.unpack("3f", vloc, 16 * k) for k in range(nv)]
            pts = []
            for q in raw:
                q = [sum(place[i][k] * q[k] for k in range(3)) + place[i][3] for i in range(3)]
                pts.append([-(q[0] - cx), q[1], q[2] - cz])
            idx = pack.unpack("%dH" % ni, iloc)
            for k in range(0, ni - 3, 4):
                tri = [pts[idx[k]], pts[idx[k + 1]], pts[idx[k + 2]]]
                mx = -(tri[0][0] + tri[1][0] + tri[2][0]) / 3 + cx
                mz = (tri[0][2] + tri[1][2] + tri[2][2]) / 3 + cz
                ab = [tri[1][i] - tri[0][i] for i in range(3)]
                ac = [tri[2][i] - tri[0][i] for i in range(3)]
                cross = [ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2], ab[0] * ac[1] - ab[1] * ac[0]]
                if x0 <= mx <= x1 and z0 <= mz <= z1 and sum(x * x for x in cross) > 1e-6:
                    collision.append(tri)
    print(f"collision from the game's meshes: {len(collision)} triangles", file=sys.stderr)
    collision_grid = None
    kept = [(t, c) for t, c in tris if t in solid]
    saved, tris[:] = tris[:], kept
    for grid in ((0.25, 0.35, 0.5, 0.7, 1.0) if not collision or len(collision) > collision_limit else ()):
        cverts, cindices = simplify(grid, False)
        collision, collision_grid = [], grid
        for a, b, c in cindices:
            pa, pb, pc = cverts[a][0], cverts[b][0], cverts[c][0]
            ab = [pb[k] - pa[k] for k in range(3)]
            ac = [pc[k] - pa[k] for k in range(3)]
            cross = [ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2], ab[0] * ac[1] - ab[1] * ac[0]]
            if sum(x * x for x in cross) > 1e-6:
                collision.append([list(pa), list(pb), list(pc)])
        print(f"collision grid {grid} m: {len(collision)} triangles", file=sys.stderr)
        if len(collision) <= collision_limit:
            break
    tris[:] = saved
    placements = [{"model": p["model"], "name": p["name"], "type": p["type"],
                   "pos": [-(p["pos"][0] - cx), p["pos"][1], p["pos"][2] - cz]}
                  for p in parts if p["type"] in (2, 4) and x0 <= p["pos"][0] <= x1 and z0 <= p["pos"][2] <= z1]
    return {"world": bytes(world), "positions": positions, "indices": [k for t in oriented for k in t],
            "collision": collision, "placements": placements, "grid": render_grid,
            "collision_grid": collision_grid,
            "triangles": len(oriented), "vertices": len(vertices), "textures": len(slot_of),
            "missing": sorted(str(t) for t in usage if t not in slot_of)}


def verify(char):
    """Unit-length check of fully dynamic quaternions over every wavelet clip of a character."""
    anims, _ = animations(char)
    worst, count = 0.0, 0
    for p in anims.values():
        loc = p.find(havok.WAVELET)[0]
        buf_loc = p.ptr(loc, 88)
        if not buf_loc:
            continue
        a = havok.wavelet_animation(p, loc)
        masks_i = p.unpack("I", loc, 64)[0]
        buf = p.d[p.at(buf_loc):]
        masks = struct.unpack_from("<%dH" % len(a["tracks"]), buf, masks_i)
        for track, m in zip(a["tracks"], masks):
            if (m >> 2) & 3 == 0 and all((m >> b) & 1 for b in (9, 10, 11, 12)):
                for q in track["rot"]:
                    worst = max(worst, abs(math.sqrt(sum(x * x for x in q)) - 1))
                    count += 1
    return len(anims), count, worst


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "verify":
        clips, samples, worst = verify(sys.argv[2])
        print(json.dumps({"clips": clips, "quaternion_samples": samples, "max_unit_error": round(worst, 6)}))
    elif command == "package":
        clips = dict(kv.split("=") for kv in sys.argv[3].split(","))
        print(json.dumps(package(sys.argv[2], clips, Path(sys.argv[4]), set(sys.argv[5].split(",")))))
    elif command == "export":
        clips = dict(kv.split("=") for kv in sys.argv[3].split(","))
        print(export(sys.argv[2], clips, Path(sys.argv[4])))
    else:
        raise SystemExit(__doc__)
