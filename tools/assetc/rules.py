"""Bounded Phase 3 vocabulary; little-endian gameplay.bin v1/v2/v3."""

import math
import re
from common import MAX_SPAWNS, u, f, string

STRINGS = ["action", "item", "npc"]
INTEGERS = {
    "health": (1, 100000),
    "resource": (1, 100000),
    "damage": (1, 100000),
    "cost": (1, 100000),
    "cooldown_ticks": (1, 1200),
    "regen_ticks": (1, 1200),
    "npc_health": (1, 100000),
    "npc_damage": (1, 100000),
    "npc_cooldown_ticks": (1, 1200),
    "respawn_ticks": (1, 1200),
    "slots": (1, 64),
    "starting_items": (0, 64),
    "reward_items": (1, 64),
    "reward_xp": (1, 100000),
    "level_xp": (1, 100000),
}
FLOATS = {
    "speed": (0.01, 3),
    "range": (0.05, 10),
    "npc_speed": (0.01, 3),
    "npc_range": (0.05, 10),
    "aggro_range": (0.05, 10),
    "leash_range": (0.05, 64),
    "spawn_x": (-1000000, 1000000),
    "spawn_z": (-1000000, 1000000),
}


MOVEMENT = {
    "run_speed": (0.01, 6),
    "backward_speed": (0.01, 6),
    "radius": (0.1, 1),
    "height": (0.5, 3),
    "step_height": (0.05, 0.5),
}


def cook(r, game, melee=False):
    if (
        set(r) - {"spawns", "interest_cell", "movement"}
        != set(STRINGS) | INTEGERS.keys() | FLOATS.keys()
    ):
        raise ValueError("gameplay vocabulary")
    for k in STRINGS:
        if not isinstance(r[k], str) or not re.fullmatch(
            re.escape(game) + r":[a-z][a-z0-9_/-]{0,95}", r[k]
        ):
            raise ValueError("gameplay namespaced ID")
    for k, (lo, hi) in INTEGERS.items():
        if (
            type(r[k]) is not int
            or not (0 if k == "cost" and melee else lo) <= r[k] <= hi
        ):
            raise ValueError("gameplay integer " + k)
    for k, (lo, hi) in FLOATS.items():
        if (
            type(r[k]) not in (int, float)
            or not math.isfinite(r[k])
            or not lo <= r[k] <= (6 if k == "speed" and "movement" in r else hi)
        ):
            raise ValueError("gameplay float " + k)
    if (
        r["cost"] > r["resource"]
        or r["starting_items"] > r["slots"]
        or r["reward_items"] > r["slots"]
        or r["aggro_range"] > r["leash_range"]
    ):
        raise ValueError("gameplay cross-field bounds")
    movement = r.get("movement")
    mode_bytes = b""
    if "movement" in r:
        if not isinstance(movement, dict) or set(movement) != set(MOVEMENT):
            raise ValueError("movement vocabulary")
        for k, (lo, hi) in MOVEMENT.items():
            v = movement[k]
            if type(v) not in (int, float) or not math.isfinite(v) or not lo <= v <= hi:
                raise ValueError("movement " + k)
        if not movement["backward_speed"] <= r["speed"] <= movement["run_speed"]:
            raise ValueError("movement speed order")
        if movement["step_height"] >= movement["height"]:
            raise ValueError("movement dimensions")
        mode_bytes = f([movement[k] for k in MOVEMENT])
    extended = "spawns" in r or "interest_cell" in r or movement is not None
    extra = b""
    if extended:
        spawns = r.get("spawns", [[r["spawn_x"], r["spawn_z"]]])
        cell = r.get("interest_cell", 1)
        if (
            type(cell) not in (float, int)
            or not math.isfinite(cell)
            or not 1 <= cell <= 64
        ):
            raise ValueError("interest cell")
        if not isinstance(spawns, list) or not 1 <= len(spawns) <= MAX_SPAWNS:
            raise ValueError("spawn count")
        for point in spawns:
            if (
                not isinstance(point, list)
                or len(point) != 2
                or any(
                    type(v) not in (int, float)
                    or not math.isfinite(v)
                    or abs(v) > 1000000
                    for v in point
                )
            ):
                raise ValueError("spawn point")
        extra = f([cell]) + u(len(spawns)) + b"".join(f(point) for point in spawns)
    return (
        (b"N3G3" if movement is not None else b"N3G2" if extended else b"N3G1")
        + b"".join(string(r[k]) for k in STRINGS)
        + b"".join(u(r[k]) for k in INTEGERS)
        + f([r[k] for k in FLOATS])
        + extra
        + mode_bytes
    )
