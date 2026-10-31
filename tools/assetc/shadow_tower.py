#!/usr/bin/env python3
"""Shadow Tower (PS1, FromSoftware, 1999) creatures from a player-supplied disc image (exploration).

    python3 tools/assetc/shadow_tower.py survey
    python3 tools/assetc/shadow_tower.py export ST/CHR1/M12.T 20 OUT_DIR idle=0,walk=1,attack=2,death=6

The disc is the user's own image (`SHADOW_TOWER_BIN`, default
~/Downloads/shadow_tower.bin), checked against a pinned hash. Nothing extracted
is committed. Formats, as observed on this disc:

- `.T` archive: u16 entry count, then count+1 u16 start offsets in 2048-byte
  sectors.
- Creature group: a model block, then its TIM(s) and a VAB sound bank.
- Multi-part model block: u32 size, u16 animation count, u16, u32 TMD offset,
  u32 part-order table offset, u32, then u32 TOD offsets from byte 24.
- The TMD holds one object per rigid part (40-byte object entries). Every
  primitive is a 24-byte textured smooth triangle without a packet header: three
  (u, v, CLUT/page) words, then (normal, vertex) u16 pairs as byte offsets
  (index x 8). Part vertices are in absolute rest-pose coordinates.
- Each TOD stream builds the skeleton in its first frame (objects, parents and
  TMD links, which index parts through the order table), then animates joint
  rotations (differential, 1/4096 degree) and root translation.

Clips are written as `gltf.cook`-subset glTF: one node per TOD object, rigid
skinning of each part to its object, LINEAR keys per game frame.
"""
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import psx  # noqa: E402

BIN_SHA256 = "420420cee70eec9d6b4c81dcf6e16494f72fc3976a93fcbe4076a7336c659adb"   # SLUS-00863
FPS = 30            # assumed game-frame rate; not confirmed against the executable
UNIT = 1 / 1000     # model units to metres (the ghoul stands about 1.8 m)
C = (-1, -1, 1)     # PS1 (y down, creatures face -Z) -> glTF (y up, face -Z): 180 degrees about Z


def disc():
    path = Path(os.environ.get("SHADOW_TOWER_BIN", "~/Downloads/shadow_tower.bin")).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"{path}: supply your own Shadow Tower (NTSC-U) disc image, or set SHADOW_TOWER_BIN")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    if h.hexdigest() != BIN_SHA256:
        raise ValueError(f"{path}: not the pinned Shadow Tower image")
    return psx.Disc(path)


def entries(data):
    n = struct.unpack_from("<H", data, 0)[0]
    offs = [struct.unpack_from("<H", data, 2 + 2 * i)[0] * 2048 for i in range(n + 1)]
    return [data[offs[i]:offs[i + 1]] for i in range(n)]


def creature(block):
    """Parts (ordered by TOD TMD id) and TOD offsets of a multi-part creature, or None."""
    if len(block) < 32:
        return None
    _size, nanim, _, tmd, order = struct.unpack_from("<IHHII", block, 0)
    if not (0 < nanim < 64 and 24 < tmd < len(block) - 12 and order < tmd):
        return None
    ident, _flags, nobj = struct.unpack_from("<III", block, tmd)
    if ident != 0x41 or not 1 < nobj < 64:
        return None
    base = tmd + 12
    objs = [struct.unpack_from("<IIIIIIi", block, base + 40 * k) for k in range(nobj)]
    parts = []
    for k, (vt, nv, nt, nn, pt, npr, _) in enumerate(objs):
        end = objs[k + 1][4] if k + 1 < nobj else objs[0][0]
        if end - pt != 24 * npr:
            return None                      # other primitive layouts are not handled
        verts = [struct.unpack_from("<hhh", block, base + vt + 8 * i) for i in range(nv)]
        norms = [struct.unpack_from("<hhh", block, base + nt + 8 * i) for i in range(nn)]
        tris = []
        for j in range(npr):
            p = base + pt + 24 * j
            u0, v0, cba, u1, v1, tsb, u2, v2 = struct.unpack_from("<BBHBBHBBxx", block, p)
            n0, i0, n1, i1, n2, i2 = struct.unpack_from("<6H", block, p + 12)
            tris.append(([(i0 // 8, n0 // 8, u0, v0), (i1 // 8, n1 // 8, u1, v1), (i2 // 8, n2 // 8, u2, v2)], cba, tsb))
        parts.append((verts, norms, tris))
    table = [struct.unpack_from("<I", block, order + 4 * k)[0] for k in range(nobj)]
    anims = [struct.unpack_from("<I", block, 24 + 4 * k)[0] for k in range(nanim)]
    return [parts[table[k] - 1] for k in range(nobj)], anims


def tims(group):
    vram, loaded = psx.VRAM(), 0
    for t in group:
        try:
            vram.load_tim(t)
            loaded += 1
        except (ValueError, struct.error):
            pass
    return vram, loaded


def atlas(vram, parts, png_path):
    """Bake each (CLUT, page) region the triangles sample into one RGB atlas; return a UV mapper."""
    regions = {}
    for _, _, tris in parts:
        for corners, cba, tsb in tris:
            r = regions.setdefault((cba, tsb), [255, 255, 0, 0])
            for _, _, u, v in corners:
                r[0], r[1], r[2], r[3] = min(r[0], u), min(r[1], v), max(r[2], u), max(r[3], v)
    width = max(r[2] - r[0] + 1 for r in regions.values())
    rows, place, y = [], {}, 0
    for key in sorted(regions):
        u0, v0, u1, v1 = regions[key]
        place[key] = (u0, v0, y)
        for v in range(v0, v1 + 1):
            rows += [psx.rgb(vram.texel(key[1], key[0], u, v)) if u <= u1 else (0, 0, 0) for u in range(u0, u0 + width)]
        y += v1 - v0 + 1
    if width > 1024 or y > 1024:
        raise ValueError("texture atlas too large")
    psx.write_png(png_path, width, y, rows)
    return lambda cba, tsb, u, v: ((u - place[(cba, tsb)][0] + .5) / width,
                                   (v - place[(cba, tsb)][1] + place[(cba, tsb)][2] + .5) / y)


def g_point(p):
    return [C[i] * p[i] * UNIT for i in range(3)]


def g_rot(m):
    """C * R * C for a PS1 rotation block."""
    return [[C[i] * m[i][j] * C[j] for j in range(3)] + [0] for i in range(3)] + [[0, 0, 0, 1]]


def export(block_group, out_dir, clips, prefix="npc"):
    """Write one glTF per clip state; return {state: (duration, strike_time)} and the attachment node."""
    block = block_group[0]
    parts, anims = creature(block)
    vram, loaded = tims(block_group[1:])
    if not loaded:
        raise ValueError("no TIM in the creature group")
    out_dir.mkdir(parents=True, exist_ok=True)
    texture = f"{prefix}-texture.png"
    uvmap = atlas(vram, parts, out_dir / texture)

    rest = psx.tod_play(psx.tod_parse(block, anims[0]))[0]
    ids = sorted(rest)
    node = {oid: i for i, oid in enumerate(ids)}
    cache = {}
    rest_world = {oid: psx.world(rest, oid, cache) for oid in ids}

    # Mesh: each part rigidly skinned to its TOD object.
    pos, nrm, uv, jnt, idx = [], [], [], [], []
    agree = 0
    for oid in ids:
        o = rest[oid]
        if o["tmd"] is None:
            continue
        verts, norms, tris = parts[o["tmd"] - 1]
        w = rest_world[oid]
        seen = {}
        for corners, cba, tsb in tris:
            out = []
            for vi, ni, u, v in corners:
                key = (vi, ni, u, v, cba, tsb)
                if key not in seen:
                    p = [sum(w[i][k] * verts[vi][k] for k in range(3)) + w[i][3] for i in range(3)]
                    n = [sum(w[i][k] * norms[ni][k] for k in range(3)) for i in range(3)]
                    length = sum(x * x for x in n) ** .5 or 1
                    seen[key] = len(pos)
                    pos.append(g_point(p))
                    nrm.append([C[i] * n[i] / length for i in range(3)])
                    uv.append(list(uvmap(cba, tsb, u, v)))
                    jnt.append(node[oid])
                out.append(seen[key])
            a, b, c = (pos[k] for k in out)
            e1, e2 = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
            face = [e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]]
            agree += sum(face[i] * sum(nrm[k][i] for k in out) for i in range(3)) > 0
            idx.append(out)
    if agree < len(idx) / 2:
        idx = [[a, c, b] for a, b, c in idx]      # counter-clockwise front faces for glTF
    idx = [k for tri in idx for k in tri]

    def g_world(m):
        r = g_rot(m)
        t = g_point([m[i][3] for i in range(3)])
        for i in range(3):
            r[i][3] = t[i]
        return r
    inverse_binds = [psx.invert_rigid(g_world(rest_world[oid])) for oid in ids]
    children = {oid: [node[k] for k in ids if rest[k]["parent"] == oid] for oid in ids}
    roots = [node[oid] for oid in ids if rest[oid]["parent"] not in rest]

    results = {}
    for state, anim in clips.items():
        frames = psx.tod_play(psx.tod_parse(block, anims[anim]))
        if len(frames) < 2:
            raise ValueError(f"{state}: clip too short")
        times = [k / FPS for k in range(len(frames))]
        tracks = []
        speed = [0.0] * len(frames)
        for oid in ids:
            ts, qs = [], []
            for k, st in enumerate(frames):
                o = st.get(oid, rest[oid])
                if o["s"] != [4096] * 3:
                    raise ValueError("animated scale is not handled")
                m = psx.rst(o)
                ts.append(g_point([m[i][3] for i in range(3)]))
                q = psx.quat(g_rot(m))
                if qs and sum(a * b for a, b in zip(q, qs[-1])) < 0:
                    q = [-x for x in q]
                if k:
                    speed[k] += 1 - abs(sum(a * b for a, b in zip(q, qs[-1])))
                qs.append(q)
            tracks += [(node[oid], "translation", ts), (node[oid], "rotation", qs)]
        duration = times[-1]
        strike = times[max(range(len(frames)), key=lambda k: speed[k])]
        write_gltf(out_dir / f"{prefix}-{state}.gltf", ids, rest, node, children, roots, pos, nrm, uv, jnt, idx,
                   inverse_binds, texture, times, tracks)
        results[state] = (round(duration, 6), round(strike, 4))
    return results, len(idx) // 3, max(p[1] for p in pos) - min(p[1] for p in pos)


def write_gltf(path, ids, rest, node, children, roots, pos, nrm, uv, jnt, idx, inverse_binds, texture, times, tracks):
    blob, views, accessors = bytearray(), [], []

    def add(data, kind, component, n):
        while len(blob) % 4:
            blob.append(0)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)})
        blob.extend(data)
        accessors.append({"bufferView": len(views) - 1, "componentType": component, "count": n, "type": kind})
        return len(accessors) - 1
    n = len(pos)
    a_pos = add(struct.pack("<%df" % (3 * n), *[v for p in pos for v in p]), "VEC3", 5126, n)
    accessors[a_pos]["min"] = [min(p[k] for p in pos) for k in range(3)]
    accessors[a_pos]["max"] = [max(p[k] for p in pos) for k in range(3)]
    a_nrm = add(struct.pack("<%df" % (3 * n), *[v for p in nrm for v in p]), "VEC3", 5126, n)
    a_uv = add(struct.pack("<%df" % (2 * n), *[v for p in uv for v in p]), "VEC2", 5126, n)
    a_j = add(struct.pack("<%dH" % (4 * n), *[v for j in jnt for v in (j, 0, 0, 0)]), "VEC4", 5123, n)
    a_w = add(struct.pack("<%df" % (4 * n), *[v for _ in jnt for v in (1, 0, 0, 0)]), "VEC4", 5126, n)
    a_i = add(struct.pack("<%dH" % len(idx), *idx), "SCALAR", 5123, len(idx))
    a_ibm = add(struct.pack("<%df" % (16 * len(inverse_binds)),
                            *[m[r][c] for m in inverse_binds for c in range(4) for r in range(4)]), "MAT4", 5126, len(ids))
    a_t = add(struct.pack("<%df" % len(times), *times), "SCALAR", 5126, len(times))
    accessors[a_t]["min"], accessors[a_t]["max"] = [times[0]], [times[-1]]
    samplers, channels = [], []
    for target, path_, values in tracks:
        width = 4 if path_ == "rotation" else 3
        a_v = add(struct.pack("<%df" % (width * len(values)), *[v for row in values for v in row]),
                  "VEC4" if width == 4 else "VEC3", 5126, len(values))
        samplers.append({"input": a_t, "output": a_v, "interpolation": "LINEAR"})
        channels.append({"sampler": len(samplers) - 1, "target": {"node": target, "path": path_}})
    nodes = []
    for oid in ids:
        m = psx.rst(rest[oid])
        entry = {"name": f"tod{oid}", "translation": g_point([m[i][3] for i in range(3)]), "rotation": psx.quat(g_rot(m))}
        if children[oid]:
            entry["children"] = children[oid]
        nodes.append(entry)
    nodes.append({"name": "mesh", "mesh": 0, "skin": 0})
    doc = {
        "asset": {"version": "2.0", "generator": "n3e shadow_tower.py (local extraction)"},
        "scene": 0, "scenes": [{"nodes": roots + [len(nodes) - 1]}], "nodes": nodes,
        "meshes": [{"primitives": [{"attributes": {"POSITION": a_pos, "NORMAL": a_nrm, "TEXCOORD_0": a_uv,
                                                   "JOINTS_0": a_j, "WEIGHTS_0": a_w}, "indices": a_i, "material": 0}]}],
        "skins": [{"joints": list(range(len(ids))), "inverseBindMatrices": a_ibm}],
        "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
        "textures": [{"source": 0}], "images": [{"uri": texture}],
        "buffers": [{"uri": path.stem + ".buffer", "byteLength": len(blob)}],
        "bufferViews": views, "accessors": accessors,
        "animations": [{"samplers": samplers, "channels": channels}],
    }
    path.write_text(json.dumps(doc))
    path.with_name(path.stem + ".buffer").write_bytes(bytes(blob))


def survey(d):
    """Multi-part creatures whose TIMs cover every textured region with the right CLUT."""
    rows = []
    folders = [f"ST/{name}" for name, (_, _, is_dir) in d.listdir(*_locate(d, "ST")).items() if is_dir]
    for folder in sorted(folders):
        for name in sorted(d.listdir(*_locate(d, folder))):
            if not name.endswith(".T"):
                continue
            es = entries(d.read(f"{folder}/{name}"))
            for i, block in enumerate(es):
                c = creature(block)
                if c:
                    parts, anims = c
                    rows.append({"file": f"{folder}/{name}", "entry": i, "parts": len(parts), "animations": len(anims),
                                 "triangles": sum(len(p[2]) for p in parts)})
    return rows


def _locate(d, folder):
    lba, size = d.root
    for part in folder.split("/"):
        lba, size, _ = d.listdir(lba, size)[part]
    return lba, size


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "survey"
    d = disc()
    if command == "survey":
        for row in survey(d):
            print(json.dumps(row))
    elif command == "export":
        file, entry, out = sys.argv[2], int(sys.argv[3]), Path(sys.argv[4])
        clips = {k: int(v) for k, v in (kv.split("=") for kv in sys.argv[5].split(","))}
        es = entries(d.read(file))
        print(json.dumps(export(es[entry:entry + 5], out, clips)))
    else:
        raise SystemExit(__doc__)
