"""Optional package-authored rest recovery; no game formulas in runtime code."""
from common import u

def cook(value):
    if set(value) != {'interval_ticks','sit_cooldown_ticks','levels'}:
        raise ValueError('rest fields')
    interval, cooldown, levels = value['interval_ticks'], value['sit_cooldown_ticks'], value['levels']
    if type(interval) is not int or not 1 <= interval <= 12000 or type(cooldown) is not int or not 0 <= cooldown <= 1200 or not 1 <= len(levels) <= 255:
        raise ValueError('rest bounds')
    data=b'N3E1'+u(interval)+u(cooldown)+u(len(levels))
    for row in levels:
        if len(row)!=4 or any(type(v) is not int or not 0 <= v <= 100000 for v in row) or row[2]==0:
            raise ValueError('rest level')
        data+=b''.join(u(v) for v in row)
    return data
