"""Optional generic melee interaction policy. Radii are gameplay data, not mesh bounds."""

import math
from common import f

FIELDS = {
    "actor_radius": (0.1, 5),
    "target_radius": (0.1, 5),
    "reach": (0, 5),
    "facing_dot": (0, 0.99),
}


def cook(policy):
    if not isinstance(policy, dict) or set(policy) != set(FIELDS):
        raise ValueError("melee vocabulary")
    for k, (lo, hi) in FIELDS.items():
        v = policy[k]
        if type(v) not in (int, float) or not math.isfinite(v) or not lo <= v <= hi:
            raise ValueError("melee " + k)
    return b"N3M1" + f([policy[k] for k in FIELDS])
