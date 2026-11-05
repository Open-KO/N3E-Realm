"""Track-only player clips (N3ST, engine 46, RQ-188). Original n3e implementation.

Every player clip (player-<state>.bin, combat-<i>.bin, player-skill-<i>.bin) is
a whole N3S1 / N3SI scene: the atlas, nodes, joints, its own tracks and the
mesh, and the client requires the atlas and mesh to be the same in every one
(content/animation.md). A package whose manifest has `"player_clips":
"tracks"` stores them once, in the first player scene, player-idle.bin, which
stays a whole scene; every other player clip is cooked as N3ST:

    magic N3ST, then the track list exactly as N3S1 carries it: u32 track
    count (0-384), then per track u32 node, u32 path (0 translation,
    1 rotation, 2 scale), u32 key count (2-4096) and per key f32 time and
    four f32 values. No trailing bytes.

The client reads the atlas, nodes, joints, mesh (with any influence table),
instance scale and attachment node from player-idle.bin, and the tracks from
the N3ST file, bounded against player-idle.bin's nodes. The sources stay
whole N3S1 / N3SI scenes (tools/assetc/ko_player.py, ko_skills.py and any
glTF cook), and the cooker refuses one whose atlas, skeleton or mesh is not
byte for byte player-idle.bin's. A package with N3ST clips is engine 46,
which needs a package that is already engine 38+ (so wire 30); a manifest
without the key cooks byte for byte as before (the same pattern as N3NM,
whose four looks clips share one atlas and mesh: npc_looks.py).
"""

import npc_looks

MAGIC = b"N3ST"
ENGINE = 46
BASE = "player-idle.bin"
MODES = ("tracks",)


def mode(manifest):
    """True when the manifest asks for track-only player clips; refuses any
    other value of `player_clips` and a package without player clips."""
    if "player_clips" not in manifest:
        return False
    if manifest["player_clips"] not in MODES:
        raise ValueError("player clips mode")
    presentation = manifest.get("presentation")
    if not isinstance(presentation, dict) or BASE not in presentation:
        raise ValueError("track-only player clips need player-idle.bin")
    return True


def tracks_only(base, clip):
    """`clip` (an N3S1 / N3SI player clip) as N3ST, after checking that its
    atlas, skeleton and mesh are `base`'s (player-idle.bin's) byte for byte."""
    if base[:4] not in (b"N3S1", b"N3SI") or clip[:4] not in (b"N3S1", b"N3SI"):
        raise ValueError("player clip magic")
    head, _, tail, _ = npc_looks.split_scene(base, "player clip")
    clip_head, tracks, clip_tail, _ = npc_looks.split_scene(clip, "player clip")
    if clip[:4] != base[:4] or clip_head != head or clip_tail != tail:
        raise ValueError("player clip atlas, skeleton or mesh differs from " + BASE)
    return MAGIC + tracks
