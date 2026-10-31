"""Bounded normal attack/defense policy, N3D1. Synthetic stats, no game IDs."""

from common import u

STATS = {
    "attack": (0, 10000),
    "defense": (0, 10000),
    "accuracy": (1, 10000),
    "evasion": (1, 10000),
}


def cook(policy):
    if (
        not isinstance(policy, dict)
        or set(policy) != {"model", "player", "npc"}
        or policy["model"] != "contested_melee_v1"
    ):
        raise ValueError("damage vocabulary/model")
    values = []
    for side in ("player", "npc"):
        stats = policy[side]
        if not isinstance(stats, dict) or set(stats) != set(STATS):
            raise ValueError("damage stats")
        for k, (lo, hi) in STATS.items():
            v = stats[k]
            if type(v) is not int or not lo <= v <= hi:
                raise ValueError("damage " + k)
            values.append(v)
    return b"N3D1" + u(1) + b"".join(u(v) for v in values)
