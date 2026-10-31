"""Generic bounded directed friend roster policy."""
from common import u

def cook(p):
    if not isinstance(p,dict)or set(p)!={'capacity','name_bytes','refresh_ticks'}:raise ValueError('friend policy vocabulary')
    values=[p[k]for k in ['capacity','name_bytes','refresh_ticks']]
    if any(type(v)is not int for v in values)or not 1<=values[0]<=24 or not 1<=values[1]<=24 or not 1<=values[2]<=1200:raise ValueError('friend policy bounds')
    return b'N3F1'+b''.join(u(v)for v in values)
