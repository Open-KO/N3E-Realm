"""Original bounded party admission policy; no game IDs in the engine."""
import math,struct
from common import u

def cook(p):
    if not isinstance(p,dict)or set(p)!={'capacity','name_bytes','level_minimum','level_maximum','level_gap','repeat_ticks'}:raise ValueError('party policy vocabulary')
    for key,lo,hi in [('capacity',2,8),('name_bytes',1,24),('level_gap',0,100),('repeat_ticks',0,1200)]:
        if type(p[key])is not int or not lo<=p[key]<=hi:raise ValueError('party '+key)
    for key in ['level_minimum','level_maximum']:
        if type(p[key])not in(int,float)or not math.isfinite(p[key])or not 0<=p[key]<=10:raise ValueError('party ratio')
    if p['level_minimum']>1 or p['level_maximum']<1:raise ValueError('party ratio range')
    return b'N3Z1'+u(p['capacity'])+u(p['name_bytes'])+struct.pack('<dd',p['level_minimum'],p['level_maximum'])+u(p['level_gap'])+u(p['repeat_ticks'])
