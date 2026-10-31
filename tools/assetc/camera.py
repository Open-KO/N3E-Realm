"""Generic optional presentation/input policy, N3V1 or N3V2; radians and n3e metres.

The four EXTENSION keys are optional as a group (PQ-012, D-143). Without them the
block cooks to N3V1 exactly as before; with them it cooks to N3V2: the N3V1
fields, then drag_vertical (u32: 0 pitch, 1 distance), distance_per_pixel,
key_pitch_rate and edge_yaw_rate (float32; a rate of 0 disables it).
"""

import math
from common import f, u

FIELDS = [
    "pitch",
    "pitch_min",
    "pitch_max",
    "distance",
    "distance_min",
    "distance_max",
    "focus_height",
    "focus_scale",
    "yaw_per_pixel",
    "pitch_per_pixel",
    "zoom_per_step",
    "clearance",
    "turn_rate",
    "hold_delay",
]


EXTENSION = ["drag_vertical", "distance_per_pixel", "key_pitch_rate", "edge_yaw_rate"]
DRAG_VERTICAL = ["pitch", "distance"]
EXTENSION_BOUNDS = {"distance_per_pixel": (0.0001, 0.5), "key_pitch_rate": (0, 6.3), "edge_yaw_rate": (0, 6.3)}


def cook(c):
    base = set(FIELDS) | {"facing_relative"}
    if not isinstance(c, dict) or set(c) not in (base, base | set(EXTENSION)):
        raise ValueError("camera fields")
    for key in FIELDS:
        if type(c[key]) not in (int, float) or not math.isfinite(c[key]):
            raise ValueError("camera finite number")
    bounds = [
        (0.05, 1.4),
        (0.05, 1.4),
        (0.05, 1.4),
        (0.5, 32),
        (0.5, 32),
        (0.5, 32),
        (0, 3),
        (0, 1),
        (0.0001, 0.05),
        (0.0001, 0.05),
        (0.01, 4),
        (0.1, 0.5),
        (0.1, 6.3),
        (0, 1),
    ]
    if any(not lo <= c[key] <= hi for key, (lo, hi) in zip(FIELDS, bounds)) or not (
        c["pitch_min"] <= c["pitch"] <= c["pitch_max"]
        and c["distance_min"] <= c["distance"] <= c["distance_max"]
        and type(c["facing_relative"]) is bool
    ):
        raise ValueError("camera policy bounds")
    body = f([c[k] for k in FIELDS]) + u(int(c["facing_relative"]))
    if "drag_vertical" not in c:
        return b"N3V1" + body
    if c["drag_vertical"] not in DRAG_VERTICAL:
        raise ValueError("camera drag_vertical")
    for key, (lo, hi) in EXTENSION_BOUNDS.items():
        if type(c[key]) not in (int, float) or not math.isfinite(c[key]) or not lo <= c[key] <= hi:
            raise ValueError("camera extension bounds")
    return (b"N3V2" + body + u(DRAG_VERTICAL.index(c["drag_vertical"]))
            + f([c[k] for k in EXTENSION[1:]]))
