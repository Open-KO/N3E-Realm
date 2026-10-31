"""Offline reader for local KO OPD object/collision data. Original n3e code.

Structure follows the pinned OpenKO tree (`N3Base/N3ShapeMgr.cpp`
`CN3ShapeMgr::Load` / `LoadCollisionData`, and the `__CellMain` / `__CellSub`
readers in `N3ShapeMgr.h`). Offline only; reference bytes are never bundled.

This step reads the **collision half** of the OPD: the map extent, the shared
collision triangle soup and the per-cell index lists that reference it. That is
the input KX-03 bakes into one client/server collision artifact, so it is read
and validated before any visual shape parsing. The embedded per-shape visual
records (`CN3Shape` / `CN3SPart`) are not decoded here; only the shape count
that follows the collision block is read, as an alignment check.
"""

from common import *
from ko_terrain import ENCODED_HEADER, HAS_HEADER, encoded_name_header

CELL_MAIN_DIVIDE = 4  # sub-cells per main cell axis
CELL_SUB_SIZE = 4  # metres per sub-cell
CELL_MAIN_SIZE = CELL_MAIN_DIVIDE * CELL_SUB_SIZE  # 16 metres
MAX_CELL_MAIN = 4096 // CELL_MAIN_SIZE  # 256
MAX_MAP_METRES = float(MAX_CELL_MAIN * CELL_MAIN_SIZE)
MAX_VERSION = 2
MAX_NAME = 30
# n3e bounds. The cooked collision artifact is capped, so an OPD that cannot fit
# is rejected here rather than silently truncated downstream.
MAX_FACES = 262144
MAX_SHAPES = 65535
OBJ_SHAPE_EXTRA = 0x1000
# Real local data carries placeholder coordinates at +/-FLT_MAX. They are finite,
# so an isfinite() check passes them; baking them would produce triangles that
# span the whole float range. Faces are classified instead of trusted.
SENTINEL_LIMIT = 1e30
# Boundary walls in real data are built as tall spans at +/-5000 metres. That is
# legitimate barrier geometry, reported so a bake can bound it deliberately.
TALL_LIMIT = 4999.0


class Reader:
    def __init__(self, data):
        self.data = data
        self.at = 0

    def take(self, n):
        if n < 0 or self.at + n > len(self.data):
            raise ValueError("OPD truncated")
        out = self.data[self.at : self.at + n]
        self.at += n
        return out

    def i32(self):
        return struct.unpack("<i", self.take(4))[0]

    def u32(self):
        return struct.unpack("<I", self.take(4))[0]

    def f32(self):
        v = struct.unpack("<f", self.take(4))[0]
        if not math.isfinite(v):
            raise ValueError("nonfinite OPD value")
        return v

    def text(self, n):
        raw = self.take(n)
        cut = raw.find(b"\0")
        if cut >= 0:
            raw = raw[:cut]
        try:
            return raw.decode("ascii")
        except UnicodeDecodeError:
            raise ValueError("non-ASCII OPD name")


def _header(r, headerless=False):
    """The OPD's version and name, as (version, name).

    The pinned 1298 client's shape manager (`005b4690`) reads an int32 version
    (`005b46d8`) and, only when it is positive (signed test `005b46de`-
    `005b46e2`, whose `JLE` goes straight to the collision call at `005b4838`),
    an int32 name length (`005b474b`) and, when that is positive, the name
    (`005b47d1`); then the collision block (`005b4bb0`), which starts with the
    width (binary). So a version-0 file has no name length: n3e reads the width
    next and returns (0, "") (PQ-275). This function leaves the name field
    `+0x40074` as it was then (binary: every access to it here lies in the
    skipped block `005b46e8`-`005b4827`); n3e's empty name is its own value
    (inference). The client has no upper version bound and also skips the name
    for a negative version (binary); n3e refuses both, its own stricter bound.
    The 1097 client's files start with the width (local-asset), so the caller
    says which layout it has: `headerless=True` returns (None, ""). A headerless
    OPD's first int32 is a float width, so no small integer is a legal value
    there; a leading 0 (a width of 0.0) is still refused as a version header, so
    the flag, never the data, picks the layout.
    """
    if headerless:
        if encoded_name_header(r.data, lambda n: False):
            raise ValueError("OPD " + ENCODED_HEADER)
        if len(r.data) >= 4 and 0 <= struct.unpack_from("<i", r.data, 0)[0] <= MAX_VERSION:
            raise ValueError("OPD " + HAS_HEADER)
        return None, ""
    if encoded_name_header(r.data, lambda n: 0 <= n <= MAX_VERSION):
        raise ValueError("OPD " + ENCODED_HEADER)
    version = r.i32()
    if not 0 <= version <= MAX_VERSION:
        raise ValueError("OPD version")
    if version == 0:
        return 0, ""
    length = r.i32()
    if not 0 <= length <= MAX_NAME:
        raise ValueError("OPD name length")
    return version, (r.text(length) if length else "")


def header_name(path):
    """The OPD's internal name, without reading the objects behind it.

    The client's shape manager keeps it at `+0x40074` and `005a3110` compares it
    with the zone's Zones.tbl column 3 (`ko_zone.check_names`).
    """
    return _header(Reader(read(pathlib.Path(path))))[1]


def load_collision(path, headerless=False):
    """Read the OPD header and collision block into portable data.

    `headerless=True` reads the pre-1264 (1097) layout, which has no version or
    name before the width; the result's `version` is then None and its `name`
    empty. The flag is never guessed from the data (`_header`).
    """
    data = read(pathlib.Path(path))
    r = Reader(data)
    version, name = _header(r, headerless)

    width, depth = r.f32(), r.f32()
    for extent in (width, depth):
        if not 0 < extent <= MAX_MAP_METRES:
            raise ValueError("OPD map size")
    if int(width) % 4 or int(depth) % 4:
        raise ValueError("OPD map size must be a multiple of 4")

    faces = r.i32()
    if not 0 <= faces <= MAX_FACES:
        raise ValueError("OPD collision face count")
    raw = r.take(faces * 3 * 12)
    values = struct.unpack("<%df" % (faces * 9), raw)
    if any(not math.isfinite(v) for v in values):
        raise ValueError("nonfinite OPD collision vertex")
    vertices = [list(values[i : i + 3]) for i in range(0, len(values), 3)]

    # Cells are stored z-major, and each main cell holds CELL_MAIN_DIVIDE^2
    # sub-cells in the same order. Sub-cell entries index the triangle soup
    # above, so every index is bounds-checked against it.
    across = int(width // CELL_MAIN_SIZE)
    down = int(depth // CELL_MAIN_SIZE)
    if not 0 < across <= MAX_CELL_MAIN or not 0 < down <= MAX_CELL_MAIN:
        raise ValueError("OPD cell grid")
    cells, referenced, indexed_faces = [], set(), 0
    for z in range(down):
        for x in range(across):
            flag = r.i32()  # 005b4bb0 keeps it as the cell's +0; 005b8570 skips 2
            if flag == 0:
                continue
            count = r.i32()
            if not 0 <= count <= MAX_SHAPES:
                raise ValueError("OPD cell shape count")
            shapes = list(struct.unpack("<%dH" % count, r.take(count * 2)))
            subs = []
            for sz in range(CELL_MAIN_DIVIDE):
                for sx in range(CELL_MAIN_DIVIDE):
                    polys = r.i32()
                    if not 0 <= polys <= MAX_FACES:
                        raise ValueError("OPD sub-cell polygon count")
                    idx = list(struct.unpack("<%dI" % (polys * 3), r.take(polys * 12)))
                    for i in idx:
                        if i >= faces * 3:
                            raise ValueError("OPD collision index out of range")
                    referenced.update(idx)
                    indexed_faces += polys
                    if polys:
                        subs.append({"x": sx, "z": sz, "faces": polys, "indices": idx})
            cells.append({"x": x, "z": z, "flag": flag, "shapes": shapes, "sub_cells": subs})

    # The shape count immediately follows the collision block. A plausible value
    # here is the alignment check for everything parsed above; the per-shape
    # visual records themselves are not decoded yet.
    shape_count = r.i32()
    if not 0 <= shape_count <= MAX_SHAPES:
        raise ValueError("OPD shape count")

    # Classify every face before anything downstream bakes it. Nothing is
    # dropped here: the counts are evidence, and KX-03 decides the treatment.
    def classify(face):
        pts = vertices[face * 3 : face * 3 + 3]
        if any(abs(c) > SENTINEL_LIMIT for p in pts for c in p):
            return "sentinel"
        a, b, c = pts
        ab = [b[k] - a[k] for k in range(3)]
        ac = [c[k] - a[k] for k in range(3)]
        cross = [
            ab[1] * ac[2] - ab[2] * ac[1],
            ab[2] * ac[0] - ab[0] * ac[2],
            ab[0] * ac[1] - ab[1] * ac[0],
        ]
        if sum(v * v for v in cross) < 1e-12:
            return "degenerate"
        if any(abs(p[1]) >= TALL_LIMIT for p in pts):
            return "tall"
        return "ok"

    used = {i // 3 for i in referenced}
    kinds = {name: [] for name in ("ok", "degenerate", "sentinel", "tall")}
    for face in range(faces):
        kinds[classify(face)].append(face)
    suspect = {
        name: {
            "faces": len(kinds[name]),
            "referenced": len(set(kinds[name]) & used),
            "examples": kinds[name][:4],
        }
        for name in ("degenerate", "sentinel", "tall")
    }

    return {
        "version": version,
        "name": name,
        "width": width,
        "depth": depth,
        "faces": faces,
        "face_kinds": suspect,
        "usable_faces": len(kinds["ok"]),
        "vertices": vertices,
        "cells": cells,
        "cell_grid": [across, down],
        "indexed_faces": indexed_faces,
        "referenced_vertices": len(referenced),
        "shape_count": shape_count,
        "parsed_bytes": r.at,
        "total_bytes": len(data),
    }


# _D3DMATERIAL9 is four D3DCOLORVALUE (4 floats each) plus a float Power = 68,
# and __Material appends six uint32 render fields = 92 bytes total: dwColorOp,
# dwColorArg1, dwColorArg2, nRenderFlags, dwSrcBlend, dwDestBlend. The layout is
# binary-confirmed: `CN3SPart::Load` (`FUN_00443440`) reads exactly 0x5c bytes
# into part offset `0x7c`, and `CN3SPart::Render` (`FUN_00443090`) tests the
# flags at part offset `0xcc` — the same 0x7c + 0x50 that puts nRenderFlags
# after the three colour-operation fields.
MATERIAL_BYTES = 92
MATERIAL_FLOATS = 17  # _D3DMATERIAL9 before the render fields
# `CN3SPart::Render` (`FUN_00443090`) acts on these bits. Only the ones a static
# bake can honour are named; the rest are carried for provenance.
RF_ALPHABLENDING = 0x1   # 004430f6: queued into the frame alpha list (PQ-379)
RF_NOTUSEFOG = 0x2       # 0044327f: SetRenderState(D3DRS_FOGENABLE, FALSE)
RF_DOUBLESIDED = 0x4     # 004432aa: SetRenderState(D3DRS_CULLMODE, D3DCULL_NONE)
RF_BOARD_Y = 0x8         # 004429b0 at 00442cc6: the part tick turns the part toward the eye about y
RF_POINTSAMPLING = 0x10  # 0043dd80: an alpha primitive's MIPFILTER POINT (PQ-379)
RF_WOBBLE = 0x20         # 004429b0: a random timer (+0xdc, +0xe0, +0xe4, _rand) turns the part
RF_NOTUSELIGHT = 0x40    # 004432da: SetRenderState(D3DRS_LIGHTING, FALSE)
RF_DIFFUSEALPHA = 0x80
RF_NOTZWRITE = 0x100
RF_NOTZBUFFER = 0x400
MAX_NAME_FIELD = 256
MAX_PARTS = 1024
MAX_TEXTURES = 64
# CN3AnimKey key types.
KEY_VECTOR3, KEY_QUATERNION = 0, 1


def _name(r, limit=MAX_NAME_FIELD):
    """Length-prefixed name, as CN3BaseFileAccess and CN3SPart write them."""
    n = r.i32()
    if n < 0 or n > limit:
        raise ValueError("OPD name length")
    return r.text(n) if n else ""


def _material(r):
    """One part's __Material. Only the fields a static bake can act on."""
    diffuse = [r.f32() for _ in range(4)]
    for _ in range(MATERIAL_FLOATS - 4):
        r.f32()
    r.u32(), r.u32(), r.u32()  # dwColorOp, dwColorArg1, dwColorArg2
    flags = r.u32()
    source, destination = r.u32(), r.u32()  # dwSrcBlend, dwDestBlend
    return {
        "render_flags": flags,
        "double_sided": bool(flags & RF_DOUBLESIDED),
        "diffuse_alpha": diffuse[3],
        # `00443090` copies +0xd0 / +0xd4 into an RF_ALPHABLENDING part's
        # alpha primitive (PQ-379).
        "source_blend": source,
        "destination_blend": destination,
    }


def _anim_key(r):
    """CN3AnimKey::Load. A non-empty track means the object animates."""
    count = r.i32()
    if count < 0 or count > 1 << 20:
        raise ValueError("OPD animation key count")
    if count == 0:
        return 0
    kind = r.i32()
    r.f32()  # sampling rate
    if kind == KEY_VECTOR3:
        r.take(12 * count)
    elif kind == KEY_QUATERNION:
        r.take(16 * count)
    else:
        raise ValueError("OPD animation key type")
    return count


def load_shapes(path, headerless=False):
    """Read the OPD's placed object records, after the collision block.

    `headerless` is as for `load_collision`.

    Returns the placements the map declares: name, transform, per-part mesh,
    material and texture references, plus the event/NPC fields. Animated and
    event-driven objects are classified rather than flattened, because their
    static pose is not what the map means by them.
    """
    collision = load_collision(path, headerless)
    data = read(pathlib.Path(path))
    r = Reader(data)
    # load_collision already consumed the shape count as its alignment check,
    # so resume immediately after it rather than reading it twice.
    r.at = collision["parsed_bytes"]
    count = collision["shape_count"]
    shapes = []
    for _ in range(count):
        kind = r.u32()
        name = _name(r)
        position = [r.f32() for _ in range(3)]
        rotation = [r.f32() for _ in range(4)]
        scale = [r.f32() for _ in range(3)]
        animated = sum(_anim_key(r) for _ in range(3))
        collision_mesh = _name(r, 512)
        climb_mesh = _name(r, 512)
        parts = []
        part_count = r.i32()
        if part_count < 0 or part_count > MAX_PARTS:
            raise ValueError("OPD part count")
        for _ in range(part_count):
            pivot = [r.f32() for _ in range(3)]
            mesh = _name(r)
            material = _material(r)
            textures = r.i32()
            fps = r.f32()
            if textures < 0 or textures > MAX_TEXTURES:
                raise ValueError("OPD texture count")
            names = [_name(r) for _ in range(textures)]
            parts.append({"pivot": pivot, "mesh": mesh, "textures": names,
                          "texture_fps": fps, **material})
        belong, event_id, event_type, npc_id, npc_status = (r.i32() for _ in range(5))
        shapes.append({
            "type": kind, "name": name, "position": position,
            "rotation": rotation, "scale": scale, "parts": parts,
            "animated_keys": animated,
            "collision_mesh": collision_mesh, "climb_mesh": climb_mesh,
            "belong": belong, "event_id": event_id, "event_type": event_type,
            "npc_id": npc_id, "npc_status": npc_status,
            "extra": bool(kind & OBJ_SHAPE_EXTRA),
        })
    return {
        "collision": collision,
        "shapes": shapes,
        "parsed_bytes": r.at,
        "total_bytes": len(data),
    }


# PQ-392 (D-205): 1298's shape manager load (`005b4690`, `005b4a2f`-`005b4a73`)
# keeps a shape with a non-zero event id (`+0x140`) visible (`+0x151` = 1) only
# when its event type (`+0x144`) is 0 or 5 (bind points and warp gates in the
# local OPDs), and its tick and render (`00443f40`, `00447680`, `004442e0`)
# draw it as any visible shape. Neither reads the NPC fields, and the `0x1000`
# kind keeps the pose `004445a0` loads until something sets a part's turn
# (PQ-391 claims 13, 14), so the `npc` and `extra` rules do not apply to them.
SHOWN_EVENT_TYPES = frozenset({0, 5})
# PQ-395 (D-206): 1298 hides every other event shape at load (`005b4a6a`), but
# its AI server builds an object NPC for an SMD object event of type 1-3 or 6-9
# with an NPC table row (`00413693`, `0043bcaa`), and the client's NPC-in then
# binds a `0x1000` shape (`005cd620`, `005ce31e`-`005ce334`) and, for event
# type 8, shows it with status 1 (`005ce447`) and no part turn, until NPC out
# hides it (`00455b70`). The only local type 8 shape is Moradon's magic anvil
# (event 5001, K_NPC 5001), whose server record's status equals the OPD's; the
# bake draws it in that in-range state, a static stand-in for the NPC's view
# range (binary + local-asset; inference, not observed: PQ-396). Types 1-3
# (turned by `00447b60`) and 6, 7, 9 (status writers by K_NPC byType) stay out.
NPC_SHOWN_EVENT_TYPES = frozenset({8})
NPC_SHOWN_STATUS = 1
# PQ-412 (D-213): a shape without an event id keeps the `+0x151` = 1 its
# constructor stores (`00443ae0` at `00443b41`; `005b4690` touches it only at
# `005b4a2f`-`005b4a73`), and its tick and render (`00443f40` at `00444226`,
# `004442e0`) tick and draw every part. The part tick cycles a multi-texture
# part whatever its flags (D-212); after it only RF_BOARD_Y and RF_WOBBLE move
# the part, so a static shape whose cycling parts have neither draws in its
# loaded pose with their sequences (`material_cycle`). One with either stays
# out (`animated_material`; PQ-413, after PQ-038's world-part Y billboards).
MATERIAL_CYCLE_REFUSED = RF_BOARD_Y | RF_WOBBLE
# The classes the KO world bake places (`ko_scene.object_geometry`).
BAKED = frozenset({"static", "event_shown", "event_npc_shown", "material_cycle"})


def cycling_parts(shape):
    """The parts 1298's part tick cycles (`004429b0`, `00442c65`-`00442cb2`):
    more than one texture, advanced at an fps above 0 (D-212)."""
    return [p for p in shape["parts"] if p["texture_fps"] > 0 and len(p["textures"]) > 1]


def classify(shape):
    """Static objects, the event shapes 1298 shows at load, the ones its
    object NPCs show (D-206) and the static ones whose cycling parts neither
    billboard nor wobble (D-213) are bakeable; the rest are excluded, with a
    reason."""
    if shape["event_id"] and shape["event_type"] in SHOWN_EVENT_TYPES:
        # Its multi-texture ("magic") part cycles its textures from the first
        # (`004425d5`, `004429b0`, `00443090`; N3W6 sequences, D-212).
        if shape["animated_keys"]:
            return "animated"
        if not any(p["mesh"] for p in shape["parts"]):
            return "empty"
        return "event_shown"
    if (shape["event_id"] and shape["event_type"] in NPC_SHOWN_EVENT_TYPES
            and shape["npc_status"] == NPC_SHOWN_STATUS and shape["extra"]):
        # Drawn as its object NPC shows it, in the loaded pose; its
        # multi-texture parts cycle as D-205's do (D-206, D-212).
        if shape["animated_keys"]:
            return "animated"
        if not any(p["mesh"] for p in shape["parts"]):
            return "empty"
        return "event_npc_shown"
    if shape["event_id"] or shape["event_type"]:
        return "event"
    if shape["npc_id"] or shape["npc_status"]:
        return "npc"
    if shape["extra"]:
        return "extra"
    if shape["animated_keys"]:
        return "animated"
    cycling = cycling_parts(shape)
    if any(p["render_flags"] & MATERIAL_CYCLE_REFUSED for p in cycling):
        return "animated_material"
    if not any(p["mesh"] for p in shape["parts"]):
        return "empty"
    return "material_cycle" if cycling else "static"


def provenance(path, parsed):
    """Reproducible manifest describing one imported OPD collision block."""
    bounds = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
    if parsed["vertices"]:
        for k in range(3):
            column = [v[k] for v in parsed["vertices"]]
            bounds[0][k], bounds[1][k] = min(column), max(column)
    return {
        "source": str(path),
        "sha256": digest(read(pathlib.Path(path))).hex(),
        "format": ("N3 OPD headerless (pre-1264)" if parsed["version"] is None
                   else "N3 OPD version %d" % parsed["version"]),
        "name": parsed["name"],
        "map_metres": [parsed["width"], parsed["depth"]],
        "cell_grid": parsed["cell_grid"],
        "collision_faces": parsed["faces"],
        "usable_faces": parsed["usable_faces"],
        "face_kinds": parsed["face_kinds"],
        "indexed_faces": parsed["indexed_faces"],
        "referenced_vertices": parsed["referenced_vertices"],
        "populated_cells": len(parsed["cells"]),
        "shape_count": parsed["shape_count"],
        "bounds": bounds,
        "parsed_bytes": parsed["parsed_bytes"],
        "total_bytes": parsed["total_bytes"],
        "notes": [
            "Collision block only; per-shape visual records are not decoded.",
            "Every sub-cell index was bounds-checked against the triangle soup.",
            "Shape count following the block was read as an alignment check.",
            "Faces are classified, never dropped here; KX-03 decides treatment.",
            "sentinel = placeholder coordinate beyond 1e30; tall = |y| >= 4999.",
        ],
    }
