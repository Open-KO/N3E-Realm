"""PQ-394 (D-212): the test client's texture-sequence log, read and replayed.

With N3E_TEST_SEQUENCE_LOG the test client prints one `WORLD_SEQUENCE` line per
frame for every sequence part its world pass draws (the last pass of a matched
capture): the frame, the part's chunk, index and centre, its advances so far,
its index and drawn frame after this frame's advance, its frame count and fps,
and the frame time used. `replay` recomputes a part's index from 0 in float32 as
the engine defines it (index + seconds x fps, 0 once it reaches the count) and
checks every logged line against it, so the rate and the reset are checked on
every frame, independently of the client's code.
"""
import struct


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def rows(out):
    """{(chunk, part): [row, ...]} of the WORLD_SEQUENCE lines in `out`."""
    parts = {}
    for line in out.splitlines():
        if line.startswith("WORLD_SEQUENCE "):
            r = dict(f.split("=", 1) for f in line.split()[1:])
            r["center"] = [float(c) for c in r["center"].split(",")]
            parts.setdefault((int(r["chunk"]), int(r["part"])), []).append(r)
    return parts


def replay(part_rows):
    """Check a part's rows against the float32 replay from index 0; return
    {frame: drawn frame index}."""
    frames, fps = int(part_rows[0]["frames"]), f32(float(part_rows[0]["fps"]))
    index, shown = 0.0, {}
    for n, r in enumerate(part_rows):
        assert int(r["frames"]) == frames and f32(float(r["fps"])) == fps, r
        index = f32(f32(f32(float(r["seconds"])) * fps) + index)
        if index >= frames:
            index = 0.0
        assert int(r["advances"]) == n + 1 and f32(float(r["index"])) == index \
            and int(r["frame_index"]) == int(index), (n, r, index)
        shown[int(r["frame"])] = int(index)
    return shown
