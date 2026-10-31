"""Original package encoding for ordered direct and physical-group item drops."""
import math
import struct
from common import u, string


def cook(p, game):
    fields = ['multiplier','increment','seed','group_bound','event_percent']
    if not isinstance(p,dict) or set(p)!=set(fields+['event_unit','premium_rate','items','rows']): raise ValueError('item drop vocabulary')
    for k,hi in zip(fields,[2**32-1,2**32-1,2**32-1,32767,255]):
        if type(p[k]) is not int or not (1 if k=='group_bound' else 0)<=p[k]<=hi: raise ValueError('item drop '+k)
    for k in ['event_unit','premium_rate']:
        if type(p[k]) not in (int,float) or not math.isfinite(p[k]) or not 0<=p[k]<=1:raise ValueError('item drop '+k)
    items=p['items'];rows=p['rows']
    if not isinstance(items,list) or not 1<=len(items)<=64 or not isinstance(rows,list) or not 1<=len(rows)<=6:raise ValueError('item drop counts')
    b=b''.join(u(p[k])for k in fields)+struct.pack('<ff',p['event_unit'],p['premium_rate'])+u(len(items))
    seen=set()
    import re
    for i in items:
        if not isinstance(i,dict) or set(i)!={'id','quantity','durability'} or not isinstance(i['id'],str) or not re.fullmatch(re.escape(game)+r':[a-z][a-z0-9_/-]{0,95}',i['id']) or i['id'] in seen:raise ValueError('drop item identity')
        seen.add(i['id'])
        if type(i['quantity']) is not int or not 1<=i['quantity']<=9999 or type(i['durability']) is not int or not 0<=i['durability']<=65535:raise ValueError('drop item bounds')
        b+=string(i['id'])+u(i['quantity'])+u(i['durability'])
    b+=u(len(rows))
    for r in rows:
        if not isinstance(r,dict) or set(r)!={'chance','level_penalty','premium','group','slots'}:raise ValueError('drop row vocabulary')
        if any(type(r[k]) is not int or not 0<=r[k]<=10000 for k in ['chance','level_penalty']) or any(type(r[k]) is not bool for k in ['premium','group']):raise ValueError('drop row bounds')
        slots=r['slots']
        if not isinstance(slots,list) or not 1<=len(slots)<=30 or any(type(v) is not int or not 0<=v<=len(items) for v in slots) or (not r['group'] and (len(slots)!=1 or slots[0]==0)):raise ValueError('drop physical slots')
        b+=b''.join(u(v)for v in [r['chance'],r['level_penalty'],int(r['premium']),int(r['group']),len(slots),*slots])
    return b
