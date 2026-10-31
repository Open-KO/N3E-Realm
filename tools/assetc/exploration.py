"""Generic immutable exploration policy; engine 13 / wire 7."""
from common import f
import math


def cook(p, lod=True):
    # An N3W2 world carries its own parts (PQ-231): no separate LOD file then.
    if set(p) != {'turbo_multiplier', 'fog_start', 'fog_end', 'fog_color'} | ({'lod'} if lod else set()):
        raise ValueError('exploration vocabulary')
    values = [p['turbo_multiplier'], p['fog_start'], p['fog_end'], *p['fog_color']]
    if len(values) != 6 or any(type(v) not in (int,float) or not math.isfinite(v) for v in values):
        raise ValueError('exploration finite values')
    m, start, end, *color = values
    if not 1 <= m <= 10 or not 0 <= start < end <= 1000 or any(not 0 <= c <= 1 for c in color):
        raise ValueError('exploration bounds')
    return b'N3X1' + f(values)
