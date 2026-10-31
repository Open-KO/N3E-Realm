"""Generic positional-sound policy appended to N3AU as N3A2 (PQ-013, D-144).

Fields (displayed metres): listener ("camera" or "character": the controlled
character's position and facing, the camera while there is none),
effect_distance with its option bounds effect_distance_min/max (effect sounds
start only while the camera eye is strictly nearer; 0 for all three disables
the test), cutoff (other positional sounds fade over the last 5 m and are
silent beyond it) and reference (full gain within, inverse distance beyond).
The client loader (client/assets/assets.cpp, load_audio) checks the same bounds.
"""

import math
from common import f, u

LISTENERS = ["camera", "character"]
FIELDS = ["listener", "effect_distance", "effect_distance_min", "effect_distance_max", "cutoff", "reference"]


def cook(c):
    """The bytes appended after the N3AU timings; raises ValueError when out of bounds."""
    if not isinstance(c, dict) or set(c) != set(FIELDS) or c["listener"] not in LISTENERS:
        raise ValueError("audio spatial fields")
    values = [c[k] for k in FIELDS[1:]]
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise ValueError("audio spatial finite number")
    distance, low, high, cutoff, reference = values
    effect = (low == high == distance == 0) or (1 <= low <= distance <= high <= 512)
    if not (effect and 5 <= cutoff <= 512 and 0.1 <= reference <= 32 and reference < cutoff):
        raise ValueError("audio spatial bounds")
    return u(LISTENERS.index(c["listener"])) + f(values)
