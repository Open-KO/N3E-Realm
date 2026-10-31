"""Ordinary positive-damage durability policy; spell variants are separate gates."""
import math,struct
from common import u,string

def cook(p,gear):
    if not isinstance(p,dict)or set(p)!={'scale','items'}:raise ValueError('wear vocabulary')
    scale=p['scale']
    if type(scale)not in(int,float)or not math.isfinite(scale)or not 0<scale<=1:raise ValueError('wear scale')
    items=p['items'];defs={i['id']:i for i in gear['items']};seen=set()
    if not isinstance(items,list)or len(items)!=len(defs):raise ValueError('wear coverage')
    out=b'N3U1'+struct.pack('<d',scale)+u(len(items))
    for item in items:
        if not isinstance(item,dict)or set(item)!={'id','attack_slots','defense_slots'}or item['id']not in defs or item['id']in seen:raise ValueError('wear item')
        seen.add(item['id']);out+=string(item['id'])
        for key in ['attack_slots','defense_slots']:
            slots=item[key]
            if not isinstance(slots,list)or len(slots)!=len(set(slots))or any(type(s)is not int or s not in defs[item['id']]['slots']for s in slots):raise ValueError('wear slots')
            out+=u(sum(1<<s for s in slots))
    return out
