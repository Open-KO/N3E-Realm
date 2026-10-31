"""Per-template NPC presentation (PQ-253, D-166). Original n3e implementation.

A package with NPC templates (N3N3) may carry a looks table, npc-looks.bin
(N3LK), and one model per table entry, npc-looks-<i>.bin (N3NM). The client
draws an NPC with the entry whose key is the entity's looks key (wire field 31).

N3LK: magic, u32 count (1-128), then per entry the key (u32 length + ASCII, a
rule ID in the package namespace), u32 flags (bit 0: the NPC's name is kept at
any range and drawn beyond the camera distance limit) and four clip records
(idle, walk, attack, death), each f32 duration, f32 blend, u32 loop_blend and
two f32 markers, bounded as animation.bin's clips are.

N3NM: an N3S1 scene whose track list is repeated four times, once per clip:
magic, u32 width, u32 height, the RGB atlas, the nodes, the joints, four track
lists, then the vertices, indices, instance scale and attachment node. The
cooker builds it from four N3S1 clips that share everything but their tracks,
so the atlas and mesh are stored and uploaded once per looks.

N3MM (engine 39, PQ-265, D-173): N3NM built from four N3SM clips (gltf.py):
an RGBA atlas and the clips' shared render runs in the tail, between the
indices and the instance scale. A package whose looks include an N3MM model is
engine 39; one with N3NM models only stays engine 38, byte for byte.

N3NI / N3MI (engine 40, PQ-283, D-176): N3NM / N3MM built from four N3SI /
N3SJ clips (gltf.py), whose shared tail carries the influence table between
the vertices and the indices. A package whose looks include one is engine
40; otherwise it stays engine 39 or 38, byte for byte.

| Clip | Model | Atlas | Render runs | Influence table |
|---|---|---|---|---|
| N3S1 | N3NM | RGB | no | no |
| N3SM | N3MM | RGBA | yes | no |
| N3SI | N3NI | RGB | no | yes |
| N3SJ | N3MI | RGBA | yes | yes |

Bounds (memory and load time): 128 entries, 16 MiB per model, 96 MiB of atlas
bytes (3 per texel in N3NM and N3NI, 4 in N3MM and N3MI) and 192 MiB of model files in all. Every template's looks key must name
an entry and every entry must be named by a template, so a package carries only
the looks its NPCs use.
"""
import math
import re
import struct

from common import MAX_FILE, digest, f, read, safe, string, u

MAX_LOOKS = 128
MAX_TEXTURE_BYTES = 96 * 1024 * 1024
MAX_MODEL_BYTES = 192 * 1024 * 1024
STATES = ("idle", "walk", "attack", "death")
NAME_ALWAYS = 1
# Clip magic: (model magic, atlas channels, engine the model needs).
KINDS = {b"N3S1": (b"N3NM", 3, 38), b"N3SM": (b"N3MM", 4, 39), b"N3SI": (b"N3NI", 3, 40), b"N3SJ": (b"N3MI", 4, 40)}


def filename(index):
    return f"npc-looks-{index}.bin"


def split_scene(data):
    """A looks clip (KINDS) as (shared head, tracks, shared tail, atlas
    bytes). The head is the atlas, nodes and joints; the tail the mesh (with
    any influence table and render runs), scale and attachment. Counts are
    bounded as the client's reader bounds them."""
    if data[:4] not in KINDS:
        raise ValueError("npc looks clip magic")
    channels = KINDS[data[:4]][1]
    at = 4

    def take(n):
        nonlocal at
        if at + n > len(data):
            raise ValueError("npc looks clip truncated")
        at += n
        return data[at - n:at]

    def count(limit, low=1):
        n = struct.unpack("<I", take(4))[0]
        if not low <= n <= limit:
            raise ValueError("npc looks clip count")
        return n

    width, height = count(1024), count(1024)
    take(width * height * channels)
    take(count(128) * 44)  # parent, translation, rotation, scale
    take(count(64) * 68)  # node, inverse bind matrix
    head = data[4:at]
    start = at
    for _ in range(count(384, 0)):
        take(8)  # node, path
        take(count(4096, 2) * 20)  # time, value
    tracks = data[start:at]
    return head, tracks, data[at:], width * height * channels


def engine(policy, root):
    """The engine a looks policy's models need (KINDS): 40 with an N3SI or
    N3SJ clip, 39 with an N3SM one, else 38. Reads only each clip's magic;
    `cook` checks the rest."""
    need = 38
    if not isinstance(policy, list):
        return need
    for entry in policy:
        for clip in (entry.get("clips") or []) if isinstance(entry, dict) else []:
            if isinstance(clip, dict) and isinstance(clip.get("source"), str):
                with open(safe(root, clip["source"]), "rb") as source:
                    need = max(need, KINDS.get(source.read(4), (None, None, 38))[2])
    return need


def duration(tracks):
    """The longest track's last key time, as the client measures a clip."""
    at, longest = 4, 0.0
    for _ in range(struct.unpack_from("<I", tracks)[0]):
        keys = struct.unpack_from("<I", tracks, at + 8)[0]
        longest = max(longest, struct.unpack_from("<f", tracks, at + 12 + (keys - 1) * 20)[0])
        at += 12 + keys * 20
    return longest


def rule_id(value, game):
    return (isinstance(value, str) and value.startswith(game + ":") and len(value) <= 128
            and re.fullmatch(r"[a-z0-9_:/-]+", value) is not None)


def clip_record(i, clip):
    if set(clip) != {"source", "duration", "blend", "loop_blend", "markers"}:
        raise ValueError("npc looks clip fields")
    length, blend, markers = clip["duration"], clip["blend"], clip["markers"]
    if (not all(type(x) in (int, float) and math.isfinite(x) for x in (length, blend))
            or not .001 <= length <= 3600 or not 0 <= blend <= 2 or type(clip["loop_blend"]) is not bool
            or not isinstance(markers, list) or len(markers) != 2
            or any(type(x) not in (int, float) or not math.isfinite(x) or (x != -1 and not 0 <= x <= length)
                   for x in markers)
            or (i in (2, 3) and clip["loop_blend"])):
        raise ValueError("npc looks clip bounds")
    return f([length, blend]) + u(clip["loop_blend"]) + f(markers)


def cook(policy, root, game, templates):
    """Returns ({package file: bytes}, {source: digest}) for the looks table and
    its models. `templates` is the N3N3 template list the table must cover."""
    if not isinstance(policy, list) or not 1 <= len(policy) <= MAX_LOOKS:
        raise ValueError("npc looks count")
    table, files, deps, keys = b"N3LK" + u(len(policy)), {}, {}, []
    texels = model_bytes = 0
    for index, entry in enumerate(policy):
        if not isinstance(entry, dict) or set(entry) != {"key", "name_always", "clips"}:
            raise ValueError("npc looks fields")
        if not rule_id(entry["key"], game) or entry["key"] in keys:
            raise ValueError("npc looks key")
        if type(entry["name_always"]) is not bool:
            raise ValueError("npc looks flags")
        clips = entry["clips"]
        if not isinstance(clips, list) or len(clips) != len(STATES):
            raise ValueError("npc looks clip set")
        keys.append(entry["key"])
        table += string(entry["key"]) + u(NAME_ALWAYS if entry["name_always"] else 0)
        parts, kinds = [], set()
        for i, clip in enumerate(clips):
            table += clip_record(i, clip)
            data = read(safe(root, clip["source"]))
            parts.append(split_scene(data))
            kinds.add(data[:4])
            deps[clip["source"]] = digest(data).hex()
            if abs(duration(parts[-1][1]) - clip["duration"]) > .001:
                raise ValueError("npc looks clip duration")
        head, _, tail, atlas = parts[0]
        if any(p[0] != head or p[2] != tail for p in parts) or len(kinds) != 1:
            raise ValueError("npc looks clips must share atlas, skeleton and mesh")
        model = KINDS[kinds.pop()][0] + head + b"".join(p[1] for p in parts) + tail
        if len(model) > MAX_FILE:
            raise ValueError("npc looks model size")
        texels += atlas
        model_bytes += len(model)
        files[filename(index)] = model
    if texels > MAX_TEXTURE_BYTES or model_bytes > MAX_MODEL_BYTES:
        raise ValueError("npc looks byte budget")
    used = {t["looks"] for t in templates}
    if used != set(keys):
        raise ValueError("npc looks must cover exactly the templates' looks keys")
    files["npc-looks.bin"] = table
    return files, deps
