"""glTF 2.0: one skinned primitive, arbitrary TRS tree and LINEAR TRS tracks.
Reject unsupported render semantics; never silently flatten unknown features.

With `materials` (NPC looks clips only, PQ-265, D-173) a mesh may also carry
up to 16 primitives over the same attributes, each with a material whose
`N3E_render_state` extension gives its render state, and an RGBA8 atlas; such
a glTF cooks to N3SM instead of N3S1 (below). Without the extension and with
an RGB atlas it cooks to N3S1 byte for byte as before.

N3SM: N3S1 with an RGBA atlas (width x height x 4 bytes) and, between the
indices and the instance scale, u32 run count (1-16) and per run u32 first
index, u32 index count, u32 flags (1 blend, 2 double-sided, 4 unlit), f32
alpha reference (a fragment whose texture alpha is not above it is
not drawn), u32 source and u32 destination blend factor (indices into
BLEND_FACTORS; 0 when the run does not blend). Runs are drawn in order and
cover the indices exactly.

N3SI / N3SJ (engine 40, PQ-283, D-176; NPC looks clips only): N3S1 / N3SM
with an influence table between the vertices and the indices. A looks glTF
may carry JOINTS_1 / WEIGHTS_1 and on (at most 16 sets, so 64 influences a
vertex); a vertex's further influences are its pairs in those sets with a
weight above 0, in set order. The table is u32 count (1 to the vertex count)
of vertices with further influences, then per vertex, in strictly increasing
order, u32 vertex, u32 n (1-60) and n pairs of u32 skin joint and f32 weight
(above 0). Each vertex's four slots and further weights sum to 1. A glTF with
no further weight cooks exactly as with JOINTS_0 / WEIGHTS_0 alone.
"""

import binascii, math, struct, zlib
from common import *


def png(data, alpha=False, limit=1024):
    """(width, height, texels) of a noninterlaced RGB8 PNG; with `alpha`,
    (width, height, texels, channels) of an RGB8 or RGBA8 one. `limit` is the
    largest side: 1024, or 2048 for the front end's models (spec 11)."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("PNG signature")
    at = 8
    compressed = bytearray()
    width = height = 0
    ended = False
    while at < len(data):
        if at + 12 > len(data):
            raise ValueError("PNG truncated")
        n = struct.unpack_from(">I", data, at)[0]
        tag = data[at + 4 : at + 8]
        b = data[at + 8 : at + 8 + n]
        if (
            at + n + 12 > len(data)
            or binascii.crc32(tag + b) & 0xFFFFFFFF
            != struct.unpack_from(">I", data, at + 8 + n)[0]
        ):
            raise ValueError("PNG CRC/length")
        if tag == b"IHDR":
            if width or n != 13:
                raise ValueError("PNG header")
            width, height, depth, color, compression, filtering, interlace = (
                struct.unpack(">IIBBBBB", b)
            )
            count(width, limit)
            count(height, limit)
            if (depth, compression, filtering, interlace) != (8, 0, 0, 0) or color not in ((2, 6) if alpha else (2,)):
                raise ValueError("PNG requires noninterlaced RGB8")
            channels = 3 if color == 2 else 4
        elif tag == b"IDAT":
            if not width:
                raise ValueError("PNG ordering")
            compressed.extend(b)
        elif tag == b"IEND":
            if n or at + n + 12 != len(data):
                raise ValueError("PNG trailing data")
            ended = True
        else:
            raise ValueError("PNG chunk unsupported")
        at += n + 12
    size = height * (width * channels + 1)
    z = zlib.decompressobj()
    raw = z.decompress(compressed, size + 1)
    if not ended or not width or len(raw) != size or not z.eof or z.unused_data:
        raise ValueError("PNG decoded length")
    out = bytearray()
    prior = bytearray(width * channels)
    stride = width * channels + 1
    for y in range(height):
        row = bytearray(raw[y * stride + 1 : (y + 1) * stride])
        mode = raw[y * stride]
        if mode > 4:
            raise ValueError("PNG filter")
        for x in range(len(row)):
            a = row[x - channels] if x >= channels else 0
            b = prior[x]
            c = prior[x - channels] if x >= channels else 0
            p = a + b - c
            ds = [abs(p - a), abs(p - b), abs(p - c)]
            paeth = [a, b, c][ds.index(min(ds))]
            row[x] = (row[x] + [0, a, b, (a + b) // 2, paeth][mode]) & 255
        out.extend(row)
        prior = row
    return (width, height, bytes(out), channels) if alpha else (width, height, bytes(out))


# Blend factor names in N3SM's index order (the GL and D3D factors they name:
# client/render/viewer.cpp, tools/assetc/ko_character.py BLEND_FACTORS).
BLEND_FACTORS = ("zero", "one", "src_color", "one_minus_src_color", "src_alpha", "one_minus_src_alpha",
                 "dst_alpha", "one_minus_dst_alpha", "dst_color", "one_minus_dst_color")
MAX_RUNS = 16
# JOINTS_n / WEIGHTS_n sets a looks clip may carry (PQ-283): 64 influences.
MAX_INFLUENCE_SETS = 16


def render_state(state):
    """N3SM run fields (flags, alpha reference, source, destination) of an
    N3E_render_state extension."""
    if (not isinstance(state, dict) or set(state) != {"alpha_reference", "blend", "double_sided", "lit"}
            or type(state["alpha_reference"]) not in (int, float) or not 0 <= state["alpha_reference"] < 1
            or any(type(state[k]) is not bool for k in ("double_sided", "lit"))
            or not (state["blend"] is None or (isinstance(state["blend"], list) and len(state["blend"]) == 2
                                               and all(b in BLEND_FACTORS for b in state["blend"])))):
        raise ValueError("render state")
    flags = (1 if state["blend"] else 0) | (2 if state["double_sided"] else 0) | (0 if state["lit"] else 4)
    factors = [BLEND_FACTORS.index(b) for b in state["blend"]] if state["blend"] else [0, 0]
    return flags, float(state["alpha_reference"]), factors[0], factors[1]


def cook(root, source, meta, materials=False, atlas=1024):
    """(scene bytes, dependencies). `materials` admits the N3SM render states
    and further joint influence sets (NPC looks clips only); every other
    caller keeps the N3S1 subset. `atlas` 2048 is the front end's (spec 11):
    its models' atlases are up to 2048 texels a side; every other caller keeps
    1024."""
    g = load(safe(root, source))
    dependencies = {source: digest(read(safe(root, source))).hex()}
    if (
        g["asset"]["version"] != "2.0"
        or (g.get("extensionsUsed") and (not materials or g["extensionsUsed"] != ["N3E_render_state"]))
        or g.get("extensionsRequired")
    ):
        raise ValueError("unsupported glTF version/extensions")

    def dep(name):
        b = read(safe(root, name))
        dependencies[name] = digest(b).hex()
        return b

    # Resolve relative URIs within the package, preserving path containment.
    parent = str(__import__("pathlib").PurePosixPath(source).parent)

    def uri(name):
        safe(root, name)
        return dep(name if parent == "." else parent + "/" + name)

    count(len(g["buffers"]), 16)
    buffers = [uri(b["uri"]) for b in g["buffers"]]
    for desc, b in zip(g["buffers"], buffers):
        if len(b) != desc["byteLength"]:
            raise ValueError("buffer byteLength")
    count(len(g["accessors"]), 1024)
    count(len(g["bufferViews"]), 1024)

    def acc(i, kind, types):
        count(i, len(g["accessors"]) - 1, 0)
        a = g["accessors"][i]
        if (
            a["type"] != kind
            or a["componentType"] not in types
            or a.get("sparse")
            or a.get("normalized")
        ):
            raise ValueError("unsupported accessor")
        vi = a["bufferView"]
        count(vi, len(g["bufferViews"]) - 1, 0)
        v = g["bufferViews"][vi]
        bi = v["buffer"]
        count(bi, len(buffers) - 1, 0)
        b = buffers[bi]
        width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[kind]
        fmt = {5126: "f", 5123: "H", 5125: "I", 5121: "B"}[a["componentType"]] * width
        size = struct.calcsize("<" + fmt)
        n = count(a["count"], 196608)
        stride = v.get("byteStride", size)
        if type(stride) is not int or stride < size or stride > 252:
            raise ValueError("stride")
        off = v.get("byteOffset", 0)
        ao = a.get("byteOffset", 0)
        length = v["byteLength"]
        if (
            any(type(x) is not int or x < 0 for x in [off, ao, length])
            or off + length > len(b)
            or ao + (n - 1) * stride + size > length
        ):
            raise ValueError("accessor bounds")
        rows = [
            list(struct.unpack_from("<" + fmt, b, off + ao + k * stride))
            for k in range(n)
        ]
        finite(rows)
        return rows

    if g.get("samplers"):
        raise ValueError("explicit texture samplers unsupported")
    nodes = g["nodes"]
    count(len(nodes), 128)
    parents = [-1] * len(nodes)
    for i, n in enumerate(nodes):
        if any(k in n for k in ["matrix", "weights", "camera", "extensions"]):
            raise ValueError("unsupported node")
        for c in n.get("children", []):
            count(c, len(nodes) - 1, 0)
            if parents[c] != -1:
                raise ValueError("multiple parents")
            parents[c] = i
    for i in range(len(nodes)):
        seen = set()
        k = i
        while k != -1:
            if k in seen:
                raise ValueError("node cycle")
            seen.add(k)
            k = parents[k]
    if len(g["skins"]) != 1 or len(g["meshes"]) != 1:
        raise ValueError("one skin/mesh subset")
    mesh_nodes = [i for i, n in enumerate(nodes) if "mesh" in n]
    if (
        len(mesh_nodes) != 1
        or nodes[mesh_nodes[0]]["mesh"] != 0
        or nodes[mesh_nodes[0]].get("skin") != 0
    ):
        raise ValueError("mesh instance")
    roots = g["scenes"][g.get("scene", 0)]["nodes"]
    if sorted(roots) != [i for i, p in enumerate(parents) if p == -1]:
        raise ValueError("all nodes must belong to selected scene")
    primitives = g["meshes"][0]["primitives"]
    if (
        not 1 <= len(primitives) <= (MAX_RUNS if materials else 1)
        or any(q.get("mode", 4) != 4 or "targets" in q or q["attributes"] != primitives[0]["attributes"]
               for q in primitives)
    ):
        raise ValueError("triangle primitive subset")
    prim = primitives[0]
    a = prim["attributes"]
    sets = sum(1 for k in a if k.startswith("JOINTS_"))
    if (not 1 <= sets <= (MAX_INFLUENCE_SETS if materials else 1)
            or set(a) != set(["POSITION", "NORMAL", "TEXCOORD_0"] + ["%s_%d" % (k, n) for k in ("JOINTS", "WEIGHTS")
                                                                      for n in range(sets)])):
        raise ValueError("attribute subset")
    pos = acc(a["POSITION"], "VEC3", [5126])
    normal = acc(a["NORMAL"], "VEC3", [5126])
    uv = acc(a["TEXCOORD_0"], "VEC2", [5126])
    joint_sets = [acc(a["JOINTS_%d" % n], "VEC4", [5121, 5123]) for n in range(sets)]
    weight_sets = [acc(a["WEIGHTS_%d" % n], "VEC4", [5126]) for n in range(sets)]
    joints, weights = joint_sets[0], weight_sets[0]
    count(len(pos), 65536)
    if any(len(x) != len(pos) for x in [normal, uv] + joint_sets + weight_sets):
        raise ValueError("attribute lengths")
    # A vertex's further influences (PQ-283): its pairs in sets 1 and on with
    # a weight above 0, in set order.
    further = [[(j, w) for n in range(1, sets) for j, w in zip(joint_sets[n][v], weight_sets[n][v]) if w > 0]
               for v in range(len(pos))]
    ix, spans = [], []
    for q in primitives:
        part = [r[0] for r in acc(q["indices"], "SCALAR", [5123, 5125])]
        if len(part) % 3 or max(part) >= len(pos):
            raise ValueError("triangle indices")
        spans.append((len(ix), len(part)))
        ix += part
    count(len(ix), 196608)
    skin = g["skins"][0]
    js = skin["joints"]
    count(len(js), 64)
    inv = acc(skin["inverseBindMatrices"], "MAT4", [5126])
    if len(inv) != len(js) or len(set(js)) != len(js):
        raise ValueError("inverse binds")
    for j in js:
        count(j, len(nodes) - 1, 0)
    for mat in inv:
        if any(abs(mat[i] - v) > 1e-6 for i, v in [(3, 0), (7, 0), (11, 0), (15, 1)]):
            raise ValueError("non-affine inverse bind")
    for v, (p, n, t, w) in enumerate(zip(pos, normal, uv, weights)):
        vector(p, 3)
        vector(n, 3)
        vector(t, 2)
        if (
            sum(x * x for x in n) < 1e-12
            or min(min(ws[v]) for ws in weight_sets) < 0
            or abs(sum(w) + sum(x for _, x in further[v]) - 1) > 1e-5
            or max(max(set_[v]) for set_ in joint_sets) >= len(js)
        ):
            raise ValueError("skin/normal")
    if (
        len(g["images"]) != 1
        or len(g["textures"]) != 1
        or g["textures"][0].get("source") != 0
    ):
        raise ValueError("one texture subset")
    states = []
    for q in primitives:
        mat = g["materials"][q["material"]]
        pbr = mat["pbrMetallicRoughness"]
        extension = mat.get("extensions", {})
        if (
            pbr.get("baseColorTexture") != {"index": 0}
            or any(
                k in mat
                for k in [
                    "normalTexture",
                    "occlusionTexture",
                    "emissiveTexture",
                ]
            )
            or ("extensions" in mat and (not materials or set(extension) != {"N3E_render_state"}))
            or mat.get("alphaMode", "OPAQUE") != "OPAQUE"
            or mat.get("doubleSided", False)
            or pbr.get("baseColorFactor", [1] * 4) != [1] * 4
        ):
            raise ValueError("material subset")
        states.append(extension.get("N3E_render_state"))
    if atlas not in (1024, 2048):
        raise ValueError("atlas bound")
    width, height, pixels, channels = png(uri(g["images"][0]["uri"]), True, atlas) if materials else (
        png(uri(g["images"][0]["uri"]), False, atlas) + (3,))
    stated = [st is not None for st in states]
    if any(stated) and not all(stated):
        raise ValueError("render state on every primitive or none")
    runs = None
    if all(stated) or channels == 4 or len(primitives) > 1:
        # N3SM: every primitive states its render state; an RGB atlas is
        # stored opaque (alpha 255).
        if not all(stated):
            raise ValueError("render state on every primitive or none")
        runs = [(first, n) + render_state(st) for (first, n), st in zip(spans, states)]
        if channels == 3:
            pixels = b"".join(pixels[i:i + 3] + b"\xff" for i in range(0, len(pixels), 3))
    table = [(v, extra) for v, extra in enumerate(further) if extra]
    magic = (b"N3SJ" if runs else b"N3SI") if table else (b"N3SM" if runs else b"N3S1")
    out = bytearray(magic + u(width) + u(height) + pixels + u(len(nodes)))
    for i, n in enumerate(nodes):
        t = vector(n.get("translation", [0, 0, 0]), 3)
        q = vector(n.get("rotation", [0, 0, 0, 1]), 4)
        s = vector(n.get("scale", [1, 1, 1]), 3)
        if min(s) <= 0 or abs(sum(x * x for x in q) - 1) > 1e-5:
            raise ValueError("node TRS")
        out += struct.pack("<i", parents[i]) + f(t + q + s)
    out += u(len(js))
    for j, iv in zip(js, inv):
        out += u(j) + f(iv)
    tracks = []
    if len(g.get("animations", [])) > 1:
        raise ValueError("one animation clip subset")
    if g.get("animations"):
        anim = g["animations"][0]
        seen = set()
        for ch in anim["channels"]:
            node = ch["target"]["node"]
            path = ch["target"]["path"]
            count(node, len(nodes) - 1, 0)
            if path not in ["translation", "rotation", "scale"] or (node, path) in seen:
                raise ValueError("animation channel")
            seen.add((node, path))
            sa = anim["samplers"][ch["sampler"]]
            if sa.get("interpolation", "LINEAR") != "LINEAR":
                raise ValueError("LINEAR interpolation only")
            times = [r[0] for r in acc(sa["input"], "SCALAR", [5126])]
            values = acc(sa["output"], "VEC4" if path == "rotation" else "VEC3", [5126])
            count(len(times), 4096, 2)
            if (
                len(times) != len(values)
                or times != sorted(set(times))
                or times[0] != 0
                or not 0 < times[-1] <= 3600
            ):
                raise ValueError("key times")
            for v in values:
                vector(v, 4 if path == "rotation" else 3)
                if (
                    path == "rotation"
                    and abs(sum(x * x for x in v) - 1) > 1e-5
                    or path == "scale"
                    and min(v) <= 0
                ):
                    raise ValueError("animation value")
            tracks.append(
                (node, ["translation", "rotation", "scale"].index(path), times, values)
            )
    count(len(tracks), 384, 0)
    out += u(len(tracks))
    for node, path, times, values in tracks:
        out += u(node) + u(path) + u(len(times))
        for t, v in zip(times, values):
            out += f([t] + (v if len(v) == 4 else v + [0]))
    out += u(len(pos))
    for p, n, t, j, w in zip(pos, normal, uv, joints, weights):
        out += f(p + n + t) + b"".join(u(x) for x in j) + f(w)
    if table:
        out += u(len(table))
        for v, extra in table:
            out += u(v) + u(len(extra)) + b"".join(u(j) + f([w]) for j, w in extra)
    out += u(len(ix)) + b"".join(u(x) for x in ix)
    if runs:
        out += u(len(runs))
        for first, n, flags, reference, src, dst in runs:
            if not n:
                raise ValueError("empty render run")
            out += u(first) + u(n) + u(flags) + f([reference]) + u(src) + u(dst)
    scale = vector(meta["instance_scale"], 3)
    if min(scale) <= 0:
        raise ValueError("instance scale")
    attachment = meta["attachment_node"]
    count(attachment, len(nodes) - 1, 0)
    out += f(scale) + u(attachment)
    return bytes(out), dependencies
