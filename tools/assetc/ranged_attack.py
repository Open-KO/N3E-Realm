"""Ranged basic attacks on combat profiles (N3RB-N3RH, PQ-416 D-216, PQ-420 D-217, PQ-421 D-218, PQ-422 D-219,
PQ-423 D-220, PQ-417 D-222, PQ-467 D-233).

A combat profile named here is a ranged basic attack: the server checks its
strike against the actor's and the target's radii summed plus `range`, in
3-D, and the client never walks into melee reach to strike under it; a Ctrl or
double click walks to half the summed radii plus `reach`. `notice` is the
client's line for a strike beyond range (empty: none). An entry's optional
`cast_ms` (PQ-420) holds the shot: both readers stretch the profile's one
attack clip to the cast time, and the server lands the strike when that clip
reaches its first marker (1298 00461ab0, 004689f0) unless the archer moves,
dies, changes weapon or the target goes. An entry's optional `ammo` (PQ-421,
D-218), `{"item": <inventory id>, "count": n}`, makes each shot need `count`
of that item in the first bag slot holding it; the server removes them in the
strike's durable commit, and `ammo_notice` is the client's line for a shot
without them. An entry's optional `skill_hit` (PQ-422, D-219),
`{"hit_rate": 1-1000, "add_damage": 0-300, "add_damage_plus": 0-10000}`,
makes the server resolve the profile's strike on an NPC as KO's type-2
(HitType 0) skill: AI Server 0040d471 -> 00443a34. An entry's optional
`cast_effect` (PQ-423, D-220), `{"clip": <effects.bin clip>, "joints":
[j, ...]}` (1-2 distinct skeleton joint indices, -1 the actor's position),
needs a cast time: the client draws the clip at those joints of the caster,
turned with its facing, from the cast start until the cast ends (1298
00583f20 -> 00479de0, 0047a710). An entry's optional `flight` (PQ-417,
D-222), `{"clip": <effects.bin clip>, "joint": j, "speed": m/s, "hit_clip":
<clip>, "hit_joint": j, "release": <audio key>}` (the last three optional),
needs a cast time: at the landing the client flies the clip from the
shooter's joint to the target's box at `speed`, turned to its direction,
then draws `hit_clip` at the target's `hit_joint` (1298 00587ac0 ->
0047a2d0, 0047a8d0, 00586fa0). An entry's optional `hold` (PQ-467, D-233),
`{"distance": 0.5-200, "plane": "3d" | "xz"}`, is the distance (on the ground
plane for `xz`) the target must be within at the shot's acceptance, its
release and its landing or its arrow's arrival, inclusive, measured from
where the archer stands then (Ebenezer's magic packet checks 004c1dbe on each
phase of an archery row). Game numbers and the text are package data; the
rules are the engine's.

Layout, little-endian: `N3RD`, u32 count 1-32, then per entry u32 profile
(1-based, distinct), f32 reach (0 to range), f32 range (0.5-100), u32 cast_ms
(0, or 101-10000), u32 ammo (0, or a 1-based inventory item index) and u32
ammo_count (0 without ammo, else 1 to the item's stack limit); then u32
notice length 0-96 and its bytes (printable ASCII), and the ammo notice the
same way. A manifest with no `ammo` and no `ammo_notice` is cooked as
PQ-420's `N3RC` (the same without the ammo fields and the second notice); the
readers also take PQ-416's `N3RB`, without cast_ms. A manifest with a
`skill_hit` on any entry is cooked as `N3RE`: `N3RD` with, per entry after
ammo_count, u32 hit (0: the basic attack's damage, 1: a type-2 skill hit),
then u32 hit_rate, add_damage and add_damage_plus (all 0 for hit 0). A
manifest with a `cast_effect` on any entry is cooked as `N3RF`: `N3RE` with,
per entry after the skill-hit fields, u32 key length 0-64 and the clip key
(printable ASCII; empty: none), then u32 joint count (0 without a key, 1-2
with one) and the joints, u32 each, index + 1 (0: the actor's position).
A manifest with a `flight` on any entry is cooked as `N3RG`: `N3RF` with,
per entry after the cast effect, u32 key length 0-64 and the flight clip key
(empty: none), u32 source joint (index + 1, 0: the actor's position; at
most 128), f32 speed (0 without a key, else 1-1000), u32 hit key length 0-64
and the hit clip key, u32 hit joint (index + 1), u32 release key length 0-64
and the audio key; without a flight key every field is 0 or empty.
A manifest with a `hold` on any entry is cooked as `N3RH`: `N3RG` with, per
entry after the flight, f32 hold distance (0: none, else 0.5-200) and u32
plane (0 3-D, 1 the ground plane; 0 without a hold).
"""
import math
import struct

from common import f, u

MAX_NOTICE = 96
CAST_MS = (101, 10000)


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def landing_ticks(clip, cast_ms):
    """D-217: ticks from the acceptance to the landing, as the server counts
    them: the clip's entry blend plus its first marker scaled by cast /
    duration, rounded up to the 50 ms tick."""
    duration, blend, marker = f32(clip['duration']), f32(clip['blend']), f32(clip['markers'][0])
    return math.ceil((blend + marker * (cast_ms / 1000) / duration) * 20)


def cast_landing(combat, profile, cast_ms):
    """The landing ticks of `profile` (1-based) cast over `cast_ms`; raises
    ValueError where both readers refuse it."""
    if type(cast_ms) is not int or not CAST_MS[0] <= cast_ms <= CAST_MS[1]:
        raise ValueError('ranged cast time')
    profiles = combat['profiles']
    own = profiles[profile - 1]
    if len(own['attacks']) != 1:
        raise ValueError('a ranged cast needs exactly one attack clip')
    clip = own['attacks'][0]
    for i, other in enumerate(profiles, 1):
        if other['ready'] == clip or (i != profile and (clip in other['attacks'] or other.get('moving') == clip)):
            raise ValueError('a ranged cast clip is used by another profile or role')
    data = combat['clips'][clip]
    if data['markers'][0] < 0:
        raise ValueError('a ranged cast clip needs a first marker')
    land = landing_ticks(data, cast_ms)
    if not 1 <= land <= math.ceil(own['interval_ms'] / 50):
        raise ValueError('a ranged cast lands after its interval')
    return land


def text(notice, what):
    if (type(notice) is not str or len(notice) > MAX_NOTICE
            or not all(' ' <= c <= '~' for c in notice)):
        raise ValueError(what)
    data = notice.encode('ascii')
    return u(len(data)) + data


def ammo_fields(entry, inventory, wear):
    """D-218: the entry's (1-based item index, count), (0, 0) without ammo."""
    if 'ammo' not in entry:
        return 0, 0
    ammo = entry['ammo']
    if type(ammo) is not dict or set(ammo) != {'item', 'count'}:
        raise ValueError('ranged ammo fields')
    items = (inventory or {}).get('items', [])
    index = next((i for i, item in enumerate(items, 1) if item['id'] == ammo['item']), 0)
    if not index:
        raise ValueError('ranged ammo item')
    item = items[index - 1]
    if item['durability'] != 0:
        raise ValueError('ranged ammo wears')
    if type(ammo['count']) is not int or not 1 <= ammo['count'] <= item['stack_limit']:
        raise ValueError('ranged ammo count')
    if wear is None:
        raise ValueError('ranged ammo needs the wear policy (its durable strike commit)')
    return index, ammo['count']


SKILL_HIT = dict(hit_rate=(1, 1000), add_damage=(0, 300), add_damage_plus=(0, 10000))


def skill_hit_fields(entry):
    """D-219: the entry's (hit, hit_rate, add_damage, add_damage_plus), all 0
    without a skill hit."""
    if 'skill_hit' not in entry:
        return 0, 0, 0, 0
    hit = entry['skill_hit']
    if type(hit) is not dict or set(hit) != set(SKILL_HIT):
        raise ValueError('ranged skill hit fields')
    for key, (low, high) in SKILL_HIT.items():
        if type(hit[key]) is not int or not low <= hit[key] <= high:
            raise ValueError('ranged skill hit ' + key)
    return 1, hit['hit_rate'], hit['add_damage'], hit['add_damage_plus']


MAX_EFFECT_KEY = 64


def cast_effect_fields(entry):
    """D-220: the entry's cast effect as bytes (an empty key and no joints
    without one)."""
    if 'cast_effect' not in entry:
        return u(0) + u(0)
    effect = entry['cast_effect']
    if type(effect) is not dict or set(effect) != {'clip', 'joints'}:
        raise ValueError('ranged cast effect fields')
    if not entry.get('cast_ms'):
        raise ValueError('a ranged cast effect needs a cast time')
    clip, joints = effect['clip'], effect['joints']
    if (type(clip) is not str or not 1 <= len(clip) <= MAX_EFFECT_KEY
            or not all(' ' <= c <= '~' for c in clip)):
        raise ValueError('ranged cast effect clip')
    if (type(joints) is not list or not 1 <= len(joints) <= 2 or len(set(joints)) != len(joints)
            or any(type(j) is not int or not -1 <= j <= 127 for j in joints)):
        raise ValueError('ranged cast effect joints')
    data = clip.encode('ascii')
    return u(len(data)) + data + u(len(joints)) + b''.join(u(j + 1) for j in joints)


def key_bytes(key, what, empty=False):
    """A printable ASCII key of 1-64 bytes (0 when `empty`) as length + bytes."""
    if (type(key) is not str or not (0 if empty else 1) <= len(key) <= MAX_EFFECT_KEY
            or not all(' ' <= c <= '~' for c in key)):
        raise ValueError(what)
    data = key.encode('ascii')
    return u(len(data)) + data


def joint_field(joint, what):
    """A skeleton joint index (-1: the actor's position) as index + 1."""
    if type(joint) is not int or not -1 <= joint <= 127:
        raise ValueError(what)
    return u(joint + 1)


SPEED = (1, 1000)


def flight_fields(entry):
    """D-222: the entry's flight as bytes (all 0 or empty without one)."""
    if 'flight' not in entry:
        return u(0) + u(0) + f([0]) + u(0) + u(0) + u(0)
    flight = entry['flight']
    if type(flight) is not dict or not {'clip', 'joint', 'speed'} <= set(flight) <= {
            'clip', 'joint', 'speed', 'hit_clip', 'hit_joint', 'release'}:
        raise ValueError('ranged flight fields')
    if not entry.get('cast_ms'):
        raise ValueError('a ranged flight needs a cast time')
    if ('hit_clip' in flight) != ('hit_joint' in flight):
        raise ValueError('a ranged flight hit needs its clip and joint')
    speed = flight['speed']
    if type(speed) not in (int, float) or not math.isfinite(speed) or not SPEED[0] <= speed <= SPEED[1]:
        raise ValueError('ranged flight speed')
    out = key_bytes(flight['clip'], 'ranged flight clip') + joint_field(flight['joint'], 'ranged flight joint') + f([speed])
    if 'hit_clip' in flight:
        out += key_bytes(flight['hit_clip'], 'ranged flight hit clip') + joint_field(flight['hit_joint'], 'ranged flight hit joint')
    else:
        out += u(0) + u(0)
    return out + key_bytes(flight.get('release', ''), 'ranged flight release', empty=True)


HOLD = (0.5, 200)
PLANES = {'3d': 0, 'xz': 1}


def hold_fields(entry):
    """D-233: the entry's hold as bytes (0 and 0 without one)."""
    if 'hold' not in entry:
        return f([0]) + u(0)
    hold = entry['hold']
    if type(hold) is not dict or set(hold) != {'distance', 'plane'}:
        raise ValueError('ranged hold fields')
    distance = hold['distance']
    if type(distance) not in (int, float) or not math.isfinite(distance) or not HOLD[0] <= distance <= HOLD[1]:
        raise ValueError('ranged hold distance')
    if hold['plane'] not in PLANES:
        raise ValueError('ranged hold plane')
    return f([distance]) + u(PLANES[hold['plane']])


def cook(value, combat, melee, inventory=None, wear=None):
    """`value` is the manifest's `ranged_attack`; `combat` its N3A5
    `combat_animation` (the profiles named), `melee` its melee policy (the
    radii both readers add), `inventory` and `wear` its inventory and wear
    policies (an ammo item's definition and the commit that removes it)."""
    if combat is None or 'upper_nodes' not in combat or melee is None:
        raise ValueError('ranged attacks need the N3A5 combat animation and the melee policy')
    if type(value) is not dict or set(value) - {'ammo_notice'} != {'profiles', 'notice'}:
        raise ValueError('ranged attack fields')
    entries, notice = value['profiles'], value['notice']
    if type(entries) is not list or not 1 <= len(entries) <= 32:
        raise ValueError('ranged attack count')
    notice = text(notice, 'ranged attack notice')
    hold = any(type(e) is dict and 'hold' in e for e in entries)
    flight = hold or any(type(e) is dict and 'flight' in e for e in entries)
    effect = flight or any(type(e) is dict and 'cast_effect' in e for e in entries)
    skill = effect or any(type(e) is dict and 'skill_hit' in e for e in entries)
    ammo = skill or 'ammo_notice' in value or any(type(e) is dict and 'ammo' in e for e in entries)
    out, seen = (b'N3RH' if hold else b'N3RG' if flight else b'N3RF' if effect else b'N3RE' if skill else b'N3RD' if ammo else b'N3RC') + u(len(entries)), set()
    for entry in entries:
        if type(entry) is not dict or set(entry) - {'cast_ms', 'ammo', 'skill_hit', 'cast_effect', 'flight', 'hold'} != {'profile', 'reach', 'range'}:
            raise ValueError('ranged attack entry')
        profile, reach, limit = entry['profile'], entry['reach'], entry['range']
        if type(profile) is not int or not 1 <= profile <= len(combat['profiles']) or profile in seen:
            raise ValueError('ranged attack profile')
        if (any(type(v) not in (int, float) or not math.isfinite(v) for v in (reach, limit))
                or not 0.5 <= limit <= 100 or not 0 <= reach <= limit):
            raise ValueError('ranged attack bounds')
        cast_ms = entry.get('cast_ms', 0)
        if cast_ms != 0 or type(cast_ms) is not int:
            cast_landing(combat, profile, cast_ms)
        seen.add(profile)
        out += u(profile) + f([reach, limit]) + u(cast_ms)
        if ammo:
            index, count = ammo_fields(entry, inventory, wear)
            out += u(index) + u(count)
        if skill:
            out += b''.join(u(v) for v in skill_hit_fields(entry))
        if effect:
            out += cast_effect_fields(entry)
        if flight:
            out += flight_fields(entry)
        if hold:
            out += hold_fields(entry)
    out += notice
    if ammo:
        out += text(value.get('ammo_notice', ''), 'ranged ammo notice')
    return out
