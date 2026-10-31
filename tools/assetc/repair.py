"""Generic durability restoration price curve; reference parameters live in packages."""
import math,struct
from common import u,f,string

def cook(p,bag):
    if not isinstance(p,dict) or set(p)!={'power','linear','offset','multiplier','items'}:raise ValueError('repair vocabulary')
    for key,lo,hi in [('power',.01,1),('linear',0,1),('multiplier',0,1)]:
        v=p[key]
        if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=hi:raise ValueError('repair curve')
    if type(p['offset']) is not int or not 0<=p['offset']<=1000000:raise ValueError('repair offset')
    items=p['items'];defs={i['id']:i for i in bag['items']}
    if not isinstance(items,list) or not 1<=len(items)<=64 or len(set(items))!=len(items) or any(i not in defs or defs[i]['durability']<=1 for i in items):raise ValueError('repair item')
    return b'N3J1'+struct.pack('<d',p['power'])+f([p['linear']])+u(p['offset'])+f([p['multiplier']])+u(len(items))+b''.join(string(i) for i in items)
