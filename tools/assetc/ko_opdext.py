"""Offline reader for a KO zone's OPDEXT (Zones.tbl column 7). Original n3e code.

The pinned OpenKO tree has no OPDEXT reader (`GameDef.h` only names the column), so
the format below comes from the client alone (`KnightOnLine.exe`, PQ-229, binary):

* `005a3110` calls `005b4ef0` on the zone's shape manager (`[EBP + 0x48]`, the
  object the OPD was just loaded into) when column 7 is not `Reserved`
  (`005a32c6`-`005a3324`), with no release in between, then compares the shape
  manager's name (`+0x40074`) with column 3 again; a mismatch appends the column 6
  file name to `Invalid Map Files` (`005a3329`-`005a3396`).
* `005b4ef0` opens the file (a failed open logs `Can't open file (read)` and
  returns without touching the manager), reads an int16 version and, when it is
  not negative, an int32 name length; a positive length reads that many bytes and
  replaces the shape manager's name with the text up to the first NUL. It then
  calls `005b52b0`; when that fails it closes the file and returns. When the
  version is positive it reads one more int32 into the manager's `+0x6c`.
* `005b52b0` reads an int16 it ignores, then the map width and depth as floats;
  unless both equal the OPD's (`+0x5c`, `+0x60`) exactly it returns false and
  reads nothing more. Otherwise it reads a face count into `+0x68` and
  `count x 0x24` bytes of triangle soup into `+0x30` (the OPD's own soup is
  `+0x64` / `+0x2c`, read by `005b4bb0`), then walks the 16 m main cells z-major
  (`16.0` at `006a4338`): an int32 flag per cell; a non-zero flag creates the
  cell if the OPD had none (`0x10c` bytes), reads an int16 that, when not
  negative, is followed by 16 sub-cells of an int32 count and `count x 12` bytes
  of vertex indices into the OPDEXT soup (sub-cell `+0x8` / `+0xc`, beside the
  OPD's `+0x0` / `+0x4`, in the OPD's sub-cell order), and finally stores the
  flag as the cell's flag (cell `+0`).

What reads the result (PQ-229, binary unless marked):

* The extension soup `+0x30` and the sub-cell `+0x8`/`+0xc` lists are read by
  `005b68f0` (`005b6b45`, `005b6b58`, `005b6b7d`, `005b6dea`, `005b7100`-`005b7120`):
  it gathers sub-cells along a segment (`005b8570` from `005b6b03`) and returns the
  nearest segment-triangle hit. Its only caller is the world wrapper `005a3a10`
  (`[ecx+0x48]`, the zone's shape manager), vtable slot `+0x68` (`006a8398`, the
  only copy of that address in the file).
* The world's slot `+0x68` is called once, in `005eae60` (`005eb1c7`, through the
  world manager `0x81878c` `+0x1c`), and slot `+0x6c` (`005a3a40` -> `005b6010`,
  OPD faces with a vertex index at most `3 x +0x6c`, only when that value is
  positive) right after it (`005eb21e`). `005eae60` takes a position, turns a
  probe through 12 directions 30 degrees apart (pi at `006a88c4` times 1/6 at
  `006a8928`) and tests 1.2 m against the OPDEXT walls, then 1.5 m against the
  limited OPD faces; on a hit it returns a moved position. Its only callers are
  the arrival paths of the packet dispatcher: `005c87c0` (the `MsgRecv_MyInfo_All`
  log string) at `005ca757`, and opcode `0x1e` in `005c5140` at `005c5341`
  (x and z read as uint16 x 0.1, `006a40d8`; WIZ_WARP by the OpenKO naming, whose
  handler has no such step). Each then re-samples the height (world slot `+0x30`)
  and places the player there (`005c3dc0`).
* Every other reader of the shape manager's collision (the cell-array users
  `005b5680`, `005b8570`, `005b8850`, `005b8d10`; the queries `005b5890`,
  `005b7180`; the world's slot `+0x64`, called four times in `005e1bf4`-`005e3386`)
  reads only the OPD soup `+0x2c` and the sub-cell `+0x0`/`+0x4` lists. A raw
  objdump scan of the shape-manager code (`005b3000`-`005bb000`) finds `+0x30` read
  only by the loader, the release and destructor and `005b68f0`; a program-wide
  scan finds no `+0x30`/`+0x68` read through a pointer loaded from `+0x48`
  (inference: an access shape outside these scans would be missed).
* `005b8570` skips cells whose flag is 2 unless its sixth argument is set.

So the OPDEXT walls do not block movement in the client: they move a player the
server has just placed (arrival and warp) away from walls within 1.2 m, with the
`+0x6c` value limiting the second probe. n3e's collision bake keeps the OPD's
faces, which is what the client's other collision and height queries read; the arrival
correction is not modelled (a client-side move of a server-chosen position; PQ-230
decides whether n3e's server must apply an equivalent placement rule in the five
OPDEXT zones). The merged state is recorded in the provenance (`merge`).

n3e strictness, all fail-closed import checks where the client would carry on
with partial data: a missing file, a negative or unknown version, a negative or
over-long name length, an empty name, extents that differ from the OPD's or are
not whole 16 m cells, a negative count, an index outside the OPDEXT soup, a
negative `+0x6c` value, truncation and trailing bytes are refused.
"""

from common import *
import ko_shapes

MAX_VERSION = 1  # 0 and 1 are the versions the client distinguishes (sign only)
MAX_NAME = ko_shapes.MAX_NAME
MAX_FACES = ko_shapes.MAX_FACES
SUB_CELLS = ko_shapes.CELL_MAIN_DIVIDE * ko_shapes.CELL_MAIN_DIVIDE
FLAG_SKIPPED = 2  # 005b8570 leaves cells with this flag out unless told otherwise


class Reader:
    def __init__(self, data):
        self.data = data
        self.at = 0

    def take(self, n):
        if n < 0 or self.at + n > len(self.data):
            raise ValueError("OPDEXT truncated")
        out = self.data[self.at:self.at + n]
        self.at += n
        return out

    def unpack(self, fmt):
        return struct.unpack("<" + fmt, self.take(struct.calcsize("<" + fmt)))


def load(path, opd):
    """Read one OPDEXT against the OPD collision it extends (`ko_shapes.load_collision`)."""
    data = read(pathlib.Path(path))
    r = Reader(data)

    (version,) = r.unpack("h")
    if not 0 <= version <= MAX_VERSION:
        raise ValueError("OPDEXT version %d" % version)
    (length,) = r.unpack("i")
    if not 0 <= length <= MAX_NAME:
        raise ValueError("OPDEXT name length %d" % length)
    name = None  # a zero length leaves the OPD's name in place (005b4ef0)
    if length:
        raw = r.take(length).split(b"\0", 1)[0]
        if not raw:
            raise ValueError("OPDEXT name is empty")
        try:
            name = raw.decode("ascii")
        except UnicodeDecodeError:
            raise ValueError("non-ASCII OPDEXT name")

    (ignored,) = r.unpack("h")  # read and not used by 005b52b0
    width, depth = r.unpack("ff")
    if [width, depth] != [opd["width"], opd["depth"]]:
        raise ValueError("OPDEXT map size %g x %g differs from the OPD's %g x %g"
                         % (width, depth, opd["width"], opd["depth"]))
    if width % ko_shapes.CELL_MAIN_SIZE or depth % ko_shapes.CELL_MAIN_SIZE:
        raise ValueError("OPDEXT map size is not whole 16 m cells")

    (faces,) = r.unpack("i")
    if not 0 <= faces <= MAX_FACES:
        raise ValueError("OPDEXT face count %d" % faces)
    values = r.unpack("%df" % (faces * 9))
    if any(not math.isfinite(v) for v in values):
        raise ValueError("nonfinite OPDEXT vertex")
    vertices = [list(values[i:i + 3]) for i in range(0, len(values), 3)]

    across = int(width // ko_shapes.CELL_MAIN_SIZE)
    down = int(depth // ko_shapes.CELL_MAIN_SIZE)
    cells, indexed = [], 0
    for z in range(down):
        for x in range(across):
            (flag,) = r.unpack("i")
            if flag == 0:
                continue
            (cell_version,) = r.unpack("h")
            subs = []
            if cell_version >= 0:
                for sz in range(ko_shapes.CELL_MAIN_DIVIDE):
                    for sx in range(ko_shapes.CELL_MAIN_DIVIDE):
                        (count,) = r.unpack("i")
                        if not 0 <= count <= MAX_FACES:
                            raise ValueError("OPDEXT sub-cell polygon count %d" % count)
                        idx = list(r.unpack("%dI" % (count * 3)))
                        if any(i >= faces * 3 for i in idx):
                            raise ValueError("OPDEXT index outside its triangle soup")
                        indexed += count
                        if count:
                            subs.append({"x": sx, "z": sz, "faces": count, "indices": idx})
            cells.append({"x": x, "z": z, "flag": flag, "cell_version": cell_version,
                          "sub_cells": subs})

    threshold = 0  # +0x6c stays 0 (005b41e0) unless a positive version sets it
    if version > 0:
        (threshold,) = r.unpack("i")
        if threshold < 0:
            raise ValueError("OPDEXT face threshold %d" % threshold)
    if r.at != len(data):
        raise ValueError("OPDEXT has %d trailing bytes" % (len(data) - r.at))

    return {
        "version": version,
        "name": name,
        "ignored": ignored,
        "width": width,
        "depth": depth,
        "faces": faces,
        "vertices": vertices,
        "cells": cells,
        "indexed_faces": indexed,
        "threshold": threshold,
        "total_bytes": len(data),
        "sha256": digest(data).hex(),
    }


def merge(opd, ext):
    """The shape manager's state after `005b4ef0` applied `ext` to the loaded OPD.

    Returns the effective name (what `005a3110` compares with column 3 again), the
    cells with their flags, the cells the OPDEXT created and re-flagged, and the
    extension layer. The OPD soup is untouched, so the faces n3e bakes are the
    OPD's; the extension soup and `+0x6c` are carried for the provenance.
    """
    flags = {(c["x"], c["z"]): c.get("flag", 1) for c in opd["cells"]}
    created, reflagged = [], []
    for cell in ext["cells"]:
        key = (cell["x"], cell["z"])
        if key not in flags:
            created.append(list(key))
        elif flags[key] != cell["flag"]:
            reflagged.append([cell["x"], cell["z"], flags[key], cell["flag"]])
        flags[key] = cell["flag"]
    return {
        "name": ext["name"] if ext["name"] is not None else opd["name"],
        "cell_flags": flags,
        "created_cells": created,
        "reflagged_cells": reflagged,
        "skipped_cells": sorted([x, z] for (x, z), f in flags.items() if f == FLAG_SKIPPED),
        "extension_faces": ext["faces"],
        "extension_vertices": ext["vertices"],
        "extension_cells": [{"x": c["x"], "z": c["z"], "sub_cells": c["sub_cells"]}
                            for c in ext["cells"] if c["sub_cells"]],
        "threshold": ext["threshold"],
        "baked_faces": opd["faces"],
    }


def provenance(path, ext, merged):
    """Reproducible record of one OPDEXT and what its merge changed."""
    return {
        "source": str(path),
        "sha256": ext["sha256"],
        "format": "N3 OPDEXT version %d" % ext["version"],
        "name": ext["name"],
        "effective_name": merged["name"],
        "map_metres": [ext["width"], ext["depth"]],
        "extension_faces": ext["faces"],
        "extension_indexed_faces": ext["indexed_faces"],
        "flagged_cells": len(ext["cells"]),
        "created_cells": len(merged["created_cells"]),
        "reflagged_cells": len(merged["reflagged_cells"]),
        "face_threshold": ext["threshold"],
        "total_bytes": ext["total_bytes"],
        "binary": "KnightOnLine.exe 005b4ef0, 005b52b0 (read), 005a3110 (name re-check)",
        "notes": [
            "Collision only: an OPDEXT carries no objects or shapes.",
            "Baked collision is the OPD's, which the client's other collision and height "
            "queries read; the extension soup is read only by 005b68f0, the "
            "arrival/warp placement probe (005eae60), which n3e does not model "
            "(open gate, PQ-230).",
            "Cell flags and the +0x6c value (the second arrival probe, 005b6010) "
            "are recorded, not baked.",
        ],
    }
