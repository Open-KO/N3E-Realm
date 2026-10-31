"""Attached characters on equipped appearance keys (PQ-328, D-186). Original n3e
implementation.

A package with appearance keys (N3V1) may carry an attachment table,
attachments.bin (N3AT), and one model per entry, attachment-<i>.bin, in the
NPC looks model formats (N3NM, N3MM, N3NI, N3MI; tools/assetc/npc_looks.py).
The client draws entry i's model on every player whose public appearance keys
(wire field 20) include the entry's key: placed on the wearer's joint each
frame, playing its own clip for the wearer's state, and lit by a shared pulse.
The server never draws it; it applies the client's checks so both readers
accept the same packages, and it stays the authority for which items a
character wears in which slot (equipment.bin), as it already is for every key.

The rule is the 2233 client's CPlayerWing (a 2233/2145 addition; KO 1298 has
none; docs/implementation/evidence/pq-328-cospre-attachments-2233.md): two
attached characters per player, a slot each, placed on a player joint, a
clip picked from the player's state, and one pulse timer per player that every
attached slot advances (0056a710, 00569590). Which items attach which model on
which joint, and how they light, is this package data.

N3AT: magic, u32 flags (bit 0: the wearer's clock advances once for each of its
attachments every frame, as 00569590 does with both slots; otherwise once per
frame), f32 rise, hold, fall, period (the pulse: intensity t / rise up to rise,
kept, falling from 1 at hold to 0 at fall, kept, the clock restarting past
period), f32 colour r, g, b (the emissive at intensity 1), u32 count (1-16),
then per entry:

  u32 key (an N3V1 key, 1-based, each at most once)
  u32 joint (the wearer's skin joint the model is placed on)
  f32 scale (the model's scale about that joint, 0.01-100)
  u32 group (0-15; a wearer draws at most one attachment per group, the one
             whose key comes last in its key list)
  u32 flags (bit 0 optional: drawn only while the client's attachment option
             is on; bit 1 emissive: the lit indices add colour x intensity)
  f32 modulate (1, 2 or 4: the lit indices' texture product scale)
  u32 lit (how many of the model's indices, from the first, are lit; a
           multiple of 3, at most the index count, and for a model with render
           runs a whole number of runs)
  four clip records (idle, walk, attack, death) as N3LK's: f32 duration,
  f32 blend, u32 loop_blend, two f32 markers

Bounds (memory and load time): 16 entries, 16 MiB per model, 32 MiB of atlas
bytes and 64 MiB of model files in all. A package with N3AT needs appearance
and render detail and is at least engine 38 (39 for an N3MM model, 40 for N3NI
or N3MI), as a looks model is, and so wire 30.

Skeletal plugs (PQ-317, D-187): an entry with flag bit 2 is the 2233 client's
CN3ChrTypePlug, a whole animated character on a hand joint (a 2233/2145
addition; docs/implementation/evidence/pq-317-skeletal-weapon-plugs-2233.md).
Its manifest entry names `plug` instead of `optional`, `emissive`, `modulate`
and `lit` (written as 0, 0, 1 and 0: a plug is always drawn, unlit, and does
not advance the pulse). After its four clip records come:

  f32 x 12  the placement: rows r00 r01 r02 t0, r10 .., r20 .. of the 3x4
            matrix taking the model's frame into the joint's (column vectors);
            terms of at most 100, determinant at least 1e-6 in size
  u32 rows (1-64), then per row: u32 kind (0 a wearer pose state 0-9, 1 a
            combat-animation clip index, 2 a skill animation), u32 id, u32 slot
            (0-3, the model clip it plays), u32 once (1: play once and hold the
            end; 0: loop); each (kind, id) once

The client draws the model at wearer frame x the joint's posed matrix x
placement x scale and plays the slot the row for the wearer's drawn clip names
on the plug's own clock: a new slot restarts, the same slot or a clip with no
row keeps playing (2233 0042df00, 00432760). The model starts on slot 0,
looped. The key's N3D2 appearance mesh may be empty.
"""
import math
import struct

from common import MAX_FILE, digest, f, read, safe, u
import npc_looks

MAX_ATTACHMENTS = 16
MAX_GROUPS = 16
MAX_TEXTURE_BYTES = 32 * 1024 * 1024
MAX_MODEL_BYTES = 64 * 1024 * 1024
PER_ATTACHMENT = 1
OPTIONAL, EMISSIVE, PLUG = 1, 2, 4
MAX_PLUG_CLIPS = 64
KINDS = {"state": 0, "combat": 1, "skill": 2}
MAGIC = b"N3AT"


def filename(index):
    return f"attachment-{index}.bin"


def engine(policy, root):
    """The engine the models need: 40 with an N3SI or N3SJ clip, 39 with an
    N3SM one, else 38 (npc_looks.KINDS). Reads only each clip's magic."""
    need = 38
    entries = policy.get("entries") if isinstance(policy, dict) else None
    for entry in entries if isinstance(entries, list) else []:
        for clip in (entry.get("clips") or []) if isinstance(entry, dict) else []:
            if isinstance(clip, dict) and isinstance(clip.get("source"), str):
                with open(safe(root, clip["source"]), "rb") as source:
                    need = max(need, npc_looks.KINDS.get(source.read(4), (None, None, 38))[2])
    return need


def number(v, low, high):
    return type(v) in (int, float) and math.isfinite(v) and low <= v <= high


def indices_and_runs(tail, influences, materials):
    """The model's index count and, with render runs, each run's index count,
    from the shared tail (npc_looks.split_scene): vertices (64 bytes each), the
    influence table, the indices, then the runs."""
    at = 0

    def take(n):
        nonlocal at
        if at + n > len(tail):
            raise ValueError("attachment model truncated")
        at += n
        return tail[at - n:at]
    vertices = struct.unpack("<I", take(4))[0]
    take(vertices * 64)
    if influences:
        for _ in range(struct.unpack("<I", take(4))[0]):
            take(4)
            take(struct.unpack("<I", take(4))[0] * 8)
    count = struct.unpack("<I", take(4))[0]
    take(count * 4)
    runs = []
    if materials:
        for _ in range(struct.unpack("<I", take(4))[0]):
            first, n = struct.unpack("<II", take(8))
            take(16)  # flags, alpha reference, source and destination blend
            runs.append((first, n))
    return count, runs


def lit_count(lit, count, runs):
    """`lit` as an index count: "all" is every index; an integer must be a
    multiple of 3 within the model and, with render runs, end on a run."""
    if lit == "all":
        return count
    if type(lit) is not int or not 0 <= lit <= count or lit % 3:
        raise ValueError("attachment lit indices")
    if runs and lit and lit not in {first + n for first, n in runs}:
        raise ValueError("attachment lit indices must end on a render run")
    return lit


def plug_record(plug, combat_clips, skill_animations):
    """A plug entry's placement and clip map bytes (PQ-317). `combat_clips` is
    the package's combat-animation clip count and `skill_animations` the set
    of its skill animation ids, which the rows' ids must name."""
    if not isinstance(plug, dict) or set(plug) != {"placement", "clips"}:
        raise ValueError("attachment plug fields")
    m = plug["placement"]
    if not isinstance(m, list) or len(m) != 12 or not all(number(v, -100, 100) for v in m):
        raise ValueError("attachment plug placement")
    det = (m[0] * (m[5] * m[10] - m[6] * m[9]) - m[1] * (m[4] * m[10] - m[6] * m[8])
           + m[2] * (m[4] * m[9] - m[5] * m[8]))
    if abs(det) < 1e-6:
        raise ValueError("attachment plug placement")
    rows = plug["clips"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_PLUG_CLIPS:
        raise ValueError("attachment plug clip map")
    out, seen = f(m) + u(len(rows)), set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"kind", "id", "slot", "once"} or row["kind"] not in KINDS:
            raise ValueError("attachment plug clip map")
        kind, ident, slot, once = KINDS[row["kind"]], row["id"], row["slot"], row["once"]
        if (type(ident) is not int or type(slot) is not int or type(once) is not bool or not 0 <= slot < 4
                or (kind, ident) in seen):
            raise ValueError("attachment plug clip map")
        if not (0 <= ident <= 9 if kind == 0 else 0 <= ident < combat_clips if kind == 1 else ident in skill_animations):
            raise ValueError("attachment plug clip %s %r" % (row["kind"], ident))
        seen.add((kind, ident))
        out += u(kind) + u(ident) + u(slot) + u(int(once))
    return out


def cook(policy, root, appearance, equipment, combat_clips=0, skill_animations=()):
    """Returns ({package file: bytes}, {source: digest}) for the attachment
    table and its models. `appearance` is the N3V1 row list, whose (item,
    slot) pairs give the keys; `equipment` the equipment policy;
    `combat_clips` and `skill_animations` what a plug's clip map may name."""
    if not isinstance(policy, dict) or set(policy) != {"clock", "color", "entries"}:
        raise ValueError("attachment fields")
    clock, color, entries = policy["clock"], policy["color"], policy["entries"]
    if (not isinstance(clock, dict) or set(clock) != {"per_attachment", "rise", "hold", "fall", "period"}
            or type(clock["per_attachment"]) is not bool
            or not all(number(clock[k], 0, 60) for k in ("rise", "hold", "fall", "period"))
            or not 0 < clock["rise"] <= clock["hold"] <= clock["fall"] <= clock["period"]):
        raise ValueError("attachment clock")
    if not isinstance(color, list) or len(color) != 3 or not all(number(c, 0, 1) for c in color):
        raise ValueError("attachment colour")
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_ATTACHMENTS:
        raise ValueError("attachment count")
    keys = {(row["item"], row["slot"]): i + 1 for i, row in enumerate(appearance)}
    table = (MAGIC + u(PER_ATTACHMENT if clock["per_attachment"] else 0)
             + f([clock["rise"], clock["hold"], clock["fall"], clock["period"]]) + f(color) + u(len(entries)))
    files, deps, used = {}, {}, set()
    texels = model_bytes = 0
    for index, entry in enumerate(entries):
        plug = isinstance(entry, dict) and "plug" in entry
        if not isinstance(entry, dict) or set(entry) != ({"item", "slot", "joint", "scale", "group", "plug", "clips"}
                                                         if plug else
                                                         {"item", "slot", "joint", "scale", "group", "optional",
                                                          "emissive", "modulate", "lit", "clips"}):
            raise ValueError("attachment entry fields")
        if plug:
            entry = dict(entry, optional=False, emissive=False, modulate=1, lit=0)
        key = keys.get((entry["item"], entry["slot"]))
        if key is None or key in used:
            raise ValueError("attachment appearance key")
        used.add(key)
        if type(entry["joint"]) is not int or not 0 <= entry["joint"] < 64:
            raise ValueError("attachment joint")
        if not number(entry["scale"], .01, 100):
            raise ValueError("attachment scale")
        if type(entry["group"]) is not int or not 0 <= entry["group"] < MAX_GROUPS:
            raise ValueError("attachment group")
        if type(entry["optional"]) is not bool or type(entry["emissive"]) is not bool:
            raise ValueError("attachment flags")
        if entry["modulate"] not in (1, 2, 4) or type(entry["modulate"]) is bool:
            raise ValueError("attachment modulate")
        clips = entry["clips"]
        if not isinstance(clips, list) or len(clips) != len(npc_looks.STATES):
            raise ValueError("attachment clip set")
        records, parts, kinds = b"", [], set()
        for i, clip in enumerate(clips):
            records += npc_looks.clip_record(i, clip)
            data = read(safe(root, clip["source"]))
            parts.append(npc_looks.split_scene(data))
            kinds.add(data[:4])
            deps[clip["source"]] = digest(data).hex()
            if abs(npc_looks.duration(parts[-1][1]) - clip["duration"]) > .001:
                raise ValueError("attachment clip duration")
        head, _, tail, atlas = parts[0]
        if any(p[0] != head or p[2] != tail for p in parts) or len(kinds) != 1:
            raise ValueError("attachment clips must share atlas, skeleton and mesh")
        kind = kinds.pop()
        model = npc_looks.KINDS[kind][0] + head + b"".join(p[1] for p in parts) + tail
        if len(model) > MAX_FILE:
            raise ValueError("attachment model size")
        count, runs = indices_and_runs(tail, kind in (b"N3SI", b"N3SJ"), kind in (b"N3SM", b"N3SJ"))
        lit = lit_count(entry["lit"], count, runs)
        texels += atlas
        model_bytes += len(model)
        files[filename(index)] = model
        table += (u(key) + u(entry["joint"]) + f([entry["scale"]]) + u(entry["group"])
                  + u((OPTIONAL if entry["optional"] else 0) | (EMISSIVE if entry["emissive"] else 0)
                      | (PLUG if plug else 0))
                  + f([entry["modulate"]]) + u(lit) + records)
        if plug:
            table += plug_record(entry["plug"], combat_clips, set(skill_animations))
    if texels > MAX_TEXTURE_BYTES or model_bytes > MAX_MODEL_BYTES:
        raise ValueError("attachment byte budget")
    del equipment  # the keys' item/slot pairs were checked against it by appearance.cook
    files["attachments.bin"] = table
    return files, deps
