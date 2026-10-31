"""Optional bounded hostile melee state machine, N3N1, reference policy N3N2 and
the template table N3N3 (PQ-249)."""
import math
import re
import struct

from common import MAX_SPAWNS, f, string, u

FIELDS = {
    "scan_ticks": (1, 1200),
    "acquire_ticks": (0, 1200),
    "stuck_ticks": (1, 1200),
    "chase_ticks": (1, 12000),
    "return_ticks": (1, 12000),
    "recovery_ticks": (1, 1200),
}
# reference_melee_v2 adds generic, package-selected behavior switches.
OPTIONS = {
    "acquisition": ("aggressive", "passive"),
}
FLAGS = ("renew_on_hit", "return_heal", "retaliate_returning")
LIMITS = {
    "return_speed_percent": (100, 300),
    "regen_interval_ticks": (0, 12000),
    "regen_divisor": (1, 1000),
    "spawn_tries": (1, 500),
}
AREA_LIMIT = 256
# reference_templates_v3 (N3N3, PQ-249): one row per NPC template; slots name one.
# PQ-251 (D-164) lifted health, level, speed and the ranges to the reference rows'
# (tools/assetc/ko_npc.py); the layout is unchanged.
MAX_TEMPLATES = 256
TEMPLATE_INTEGERS = {
    "health": (1, 2000000),
    "level": (1, 255),
    # PQ-252 (D-165): the rows' iExp, sDamage (fixed damage and N3D1 attack)
    # and the shorts sAc, sHitRate and sEvadeRate; 0 is allowed for each.
    "xp": (0, 50000000),
    "damage": (0, 100000),
    "attack": (0, 10000),
    "defense": (0, 32767),
    "accuracy": (0, 32767),
    "evasion": (0, 32767),
    "attack_ticks": (1, 1200),
}
TEMPLATE_FLOATS = {
    "speed": (0, 12),  # m/s; 0 never moves (KO bySpeed2 0)
    "attack_range": (0.05, 64),
    "search_range": (0.05, 64),
    "tracing_range": (0.05, 64),
}
# PQ-272 (D-179): the drawn scale, an integer percent (KO sSize: AI 00438c42
# copies it to the record, 004221d5 sends it, the client's NPC-in multiplies it
# by 0.01 at 005cdd82). A policy with any `scale` cooks as N3N4 (model 4):
# N3N3 with a u32 scale after each template's tracing range, 100 where a
# template has no `scale`; the package is then engine 41.
SCALE = (1, 1000)
DEFAULT_SCALE = 100


def scaled(policy):
    """True when an N3N3 policy carries a drawn scale (N3N4, engine 41)."""
    templates = policy.get("templates") if isinstance(policy, dict) else None
    return isinstance(templates, list) and any(isinstance(t, dict) and "scale" in t for t in templates)


def _int(value, lo, hi, name):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError("npc " + name)
    return value


def _template(t, game, scale=False):
    keys = {"name", "looks", "acquisition", *TEMPLATE_INTEGERS, *TEMPLATE_FLOATS}
    if not isinstance(t, dict) or set(t) - {"scale"} != keys:
        raise ValueError("npc template vocabulary")
    for key in ("name", "looks"):
        if not isinstance(t[key], str) or (game is not None and not re.fullmatch(
                re.escape(game) + r":[a-z][a-z0-9_/-]{0,95}", t[key])):
            raise ValueError("npc template " + key)
    out = string(t["name"]) + string(t["looks"])
    for key, (lo, hi) in TEMPLATE_INTEGERS.items():
        out += u(_int(t[key], lo, hi, "template " + key))
    if t["acquisition"] not in OPTIONS["acquisition"]:
        raise ValueError("npc template acquisition")
    out += u(OPTIONS["acquisition"].index(t["acquisition"]))
    for key, (lo, hi) in TEMPLATE_FLOATS.items():
        v = t[key]
        if type(v) not in (int, float) or not math.isfinite(v) or not lo <= v <= hi:
            raise ValueError("npc template " + key)
        out += f([v])
    if t["search_range"] > t["tracing_range"]:
        raise ValueError("npc template ranges")
    if scale:
        out += u(_int(t.get("scale", DEFAULT_SCALE), *SCALE, "template scale"))
    return out


def cook(policy, spawns=None, game=None):
    if not isinstance(policy, dict):
        raise ValueError("npc vocabulary/model")
    if policy.get("model") == "hostile_melee_v1":
        if set(policy) != {"model", *FIELDS}:
            raise ValueError("npc vocabulary/model")
        for key, (lo, hi) in FIELDS.items():
            _int(policy[key], lo, hi, key)
        return b"N3N1" + u(1) + b"".join(u(policy[key]) for key in FIELDS)
    templated = policy.get("model") == "reference_templates_v3"
    if policy.get("model") != "reference_melee_v2" and not templated:
        raise ValueError("npc vocabulary/model")
    # N3N3 moves the acquisition into each template.
    keys = {"model", "slots", *FIELDS, *FLAGS, *LIMITS} | ({"templates"} if templated else set(OPTIONS))
    if set(policy) != keys:
        raise ValueError("npc vocabulary/model")
    scale = templated and scaled(policy)
    out = (b"N3N4" + u(4) if scale else b"N3N3" + u(3)) if templated else b"N3N2" + u(2)
    for key, (lo, hi) in FIELDS.items():
        out += u(_int(policy[key], lo, hi, key))
    if not templated:
        for key, choices in OPTIONS.items():
            if policy[key] not in choices:
                raise ValueError("npc " + key)
            out += u(choices.index(policy[key]))
    for key in FLAGS:
        if type(policy[key]) is not bool:
            raise ValueError("npc " + key)
        out += u(int(policy[key]))
    for key, (lo, hi) in LIMITS.items():
        out += u(_int(policy[key], lo, hi, key))
    names = []
    if templated:
        templates = policy["templates"]
        if not isinstance(templates, list) or not 1 <= len(templates) <= MAX_TEMPLATES:
            raise ValueError("npc templates")
        out += u(len(templates))
        for t in templates:
            out += _template(t, game, scale)
            if t["name"] in names:
                raise ValueError("npc template names")
            names.append(t["name"])
    slots = policy["slots"]
    # One slot per gameplay spawn point, in the same order.
    if not isinstance(slots, list) or not 1 <= len(slots) <= MAX_SPAWNS or (spawns is not None and len(slots) != len(spawns)):
        raise ValueError("npc slots")
    out += u(len(slots))
    for slot in slots:
        if not isinstance(slot, dict) or set(slot) != {"area", "respawn_ticks", *(["template"] if templated else [])}:
            raise ValueError("npc slot vocabulary")
        area = slot["area"]
        # Integer offsets from the slot's spawn point: [min x, min z, max x, max z].
        if (not isinstance(area, list) or len(area) != 4
                or any(type(v) is not int or not -AREA_LIMIT <= v <= AREA_LIMIT for v in area)
                or area[0] > 0 or area[1] > 0 or area[2] < 0 or area[3] < 0):
            raise ValueError("npc slot area")
        out += b"".join(struct.pack("<i", v) for v in area)
        out += u(_int(slot["respawn_ticks"], 1, 12000, "slot respawn_ticks"))
        if templated:
            if slot["template"] not in names:
                raise ValueError("npc slot template")
            out += u(names.index(slot["template"]))
    return out
