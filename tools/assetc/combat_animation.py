"""Bounded equipment-selected animation and interval profiles (N3A4/N3A5)."""
from common import u, f
import math

MAX_BYTES=32*1024*1024

def filename(index):return f'combat-{index}.bin'

def cook(value, inventory, equipment):
    layered='upper_nodes' in value
    if set(value)!=({'clips','profiles','slots','rows','upper_nodes'} if layered else {'clips','profiles','slots','rows'}):raise ValueError('combat animation fields')
    clips,profiles,slots,rows=(value[k]for k in ['clips','profiles','slots','rows'])
    if not 1<=len(clips)<=64 or not 1<=len(profiles)<=32 or not 1<=len(slots)<=4 or not 1<=len(rows)<=256:raise ValueError('combat animation counts')
    if len(set(slots))!=len(slots) or any(type(s)is not int or not 0<=s<len(equipment['slots'])for s in slots):raise ValueError('combat selector slots')
    out=(b'N3A5' if layered else b'N3A4')+u(len(clips))
    for clip in clips:
        if set(clip)!={'source','duration','blend','loop_blend','markers'}:raise ValueError('combat clip fields')
        d,b,loop,markers=(clip[k]for k in ['duration','blend','loop_blend','markers'])
        if not all(type(v)in(int,float)and math.isfinite(v)for v in [d,b,*markers]) or not .001<=d<=3600 or not 0<=b<=2 or type(loop)is not bool or len(markers)!=2 or any(v!=-1 and not 0<=v<=d for v in markers):raise ValueError('combat clip bounds')
        out+=f([d,b])+u(loop)+f(markers)
    out+=u(len(profiles));used=set()
    for p in profiles:
        if set(p)!=({'ready','attacks','interval_ms','moving'} if layered else {'ready','attacks'}) or not 1<=len(p['attacks'])<=4 or len(set(p['attacks']))!=len(p['attacks']):raise ValueError('combat profile')
        if any(type(i)is not int or not 0<=i<len(clips)for i in [p['ready'],*p['attacks']]):raise ValueError('combat profile clip')
        if any(clips[i]['loop_blend']for i in p['attacks']):raise ValueError('combat attack loop')
        used.update([p['ready'],*p['attacks']]);out+=u(p['ready'])+u(len(p['attacks']))+b''.join(u(i)for i in p['attacks'])
        if layered:
            ms,moving=p['interval_ms'],p['moving']
            if type(ms)is not int or not 50<=ms<=60000 or type(moving)is not int or not 0<=moving<len(clips) or clips[moving]['loop_blend']:raise ValueError('combat motion bounds')
            used.add(moving);out+=u(ms)+u(moving)
    if len(used)!=len(clips):raise ValueError('unused combat clip')
    out+=u(len(slots))+b''.join(u(s)for s in slots)+u(len(rows));seen=set();empty=False
    items={i['id']:n+1 for n,i in enumerate(inventory['items'])};gear={i['id']:i for i in equipment['items']}
    for row in rows:
        if set(row)!={'items','profile'} or len(row['items'])!=len(slots) or type(row['profile'])is not int or not 1<=row['profile']<=len(profiles):raise ValueError('combat row')
        keys=[]
        for item,slot in zip(row['items'],slots):
            if item is None:keys.append(0)
            elif item not in items or item not in gear or slot not in gear[item]['slots']:raise ValueError('combat equipment mapping')
            else:keys.append(items[item])
        key=tuple(keys)
        if key in seen:raise ValueError('duplicate combat row')
        seen.add(key);empty|=not any(keys)
        out+=b''.join(u(i)for i in keys)+u(row['profile'])
    if not empty:raise ValueError('combat empty fallback')
    if layered:
        nodes=value['upper_nodes']
        if not 1<=len(nodes)<=63 or len(set(nodes))!=len(nodes) or any(type(i)is not int or not 1<=i<64 for i in nodes):raise ValueError('combat upper mask')
        out+=u(len(nodes))+b''.join(u(i)for i in nodes)
    return out
