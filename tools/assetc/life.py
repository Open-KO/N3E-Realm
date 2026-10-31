"""Optional requested respawn and independent NPC lifetime policy, N3L1."""

from common import u

FIELDS = {
    "player_delay_ticks": (0, 1200),
    "npc_corpse_ticks": (0, 1200),
    "npc_respawn_ticks": (1, 12000),
}


def cook(policy):
    if (
        not isinstance(policy, dict)
        or set(policy) != {"model", *FIELDS}
        or policy["model"] != "requested_v1"
    ):
        raise ValueError("life vocabulary/model")
    for key, (lo, hi) in FIELDS.items():
        if type(policy[key]) is not int or not lo <= policy[key] <= hi:
            raise ValueError("life " + key)
    if policy["npc_corpse_ticks"] > policy["npc_respawn_ticks"]:
        raise ValueError("corpse exceeds NPC lifetime")
    return b"N3L1" + u(1) + b"".join(u(policy[key]) for key in FIELDS)
