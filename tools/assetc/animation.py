"""Bounded, cosmetic whole-body clip metadata; source rates are baked into seconds."""
from common import f, u
import math

STATES = ['idle', 'walk', 'attack', 'death', 'run', 'backward', 'ready']
NAMES = [f'{role}-{state}.bin' for role in ['player', 'npc']
         for state in (STATES if role == 'player' else STATES[:4])]

REST_STATES = ['sit-down','sit-idle','stand-up']
def names(count):
    return NAMES[:7]+[f'player-{s}.bin' for s in REST_STATES]+NAMES[7:] if count==14 else NAMES[:count]

def cook(value):
    if not isinstance(value, list) or len(value) not in (7, 11, 14):
        raise ValueError('animation clip set')
    data = b'N3A3' if len(value)==14 else b'N3A2' if len(value) == 7 else b'N3A1'
    for i, clip in enumerate(value):
        if set(clip) != {'duration', 'blend', 'loop_blend', 'markers'}:
            raise ValueError('animation fields')
        duration, blend = clip['duration'], clip['blend']
        markers = clip['markers']
        if (not all(type(x) in (int, float) and math.isfinite(x) for x in [duration, blend])
            or not .001 <= duration <= 3600 or not 0 <= blend <= 2
            or type(clip['loop_blend']) is not bool or len(markers) != 2
            or any(type(x) not in (int, float) or not math.isfinite(x)
                   or (x != -1 and not 0 <= x <= duration) for x in markers)
            or (i in ([2,3,7,9,12,13] if len(value)==14 else [2,3,9,10]) and clip['loop_blend'])):
            raise ValueError('animation bounds')
        data += f([duration, blend]) + u(clip['loop_blend']) + f(markers)
    return data
