"""Package-defined equipment polynomial coefficients and item bonuses."""
import math,struct,re
from common import u,f,string
# The ordered vocabulary is the binary layout. Formula constants belong to packages.
INTS={'primary':15,'secondary':15,'dual_wield':1,'dexterity_attack':1,'weapon_floor':100,'attack_base':100,'attack_offset':255,'broken_weapon_divisor':100,'broken_raw_divisor':100,'strength_threshold':255,'stamina_threshold':255,'weight_scale':1000,'rate_initial':10000}
FLOATS={'secondary_scale':1,'attack_linear':1,'defense_coefficient':10,'accuracy_coefficient':1,'evasion_coefficient':1,'strength_attack':10,'stamina_defense':10,'rate_scale':1,'rate_base':100}
POLYS=['health','mana','stamina_resource']
BONUSES={'attack':10000,'defense':10000,'health':10000,'resource':10000,'accuracy':1000,'evasion':1000}

def cook(p,bag,gear,game):
    if not isinstance(p,dict) or set(p)!=set(INTS)|set(FLOATS)|set(POLYS)|{'categories','items'}:raise ValueError('stats vocabulary')
    def number(v,lo,hi):
        if type(v)is not int or not lo<=v<=hi:raise ValueError('stats integer')
        return u(v)
    def real(v,hi,double=False):
        if type(v)not in (int,float)or not math.isfinite(v)or not 0<=v<=hi:raise ValueError('stats coefficient')
        return struct.pack('<d',v)if double else f([v])
    out=b'N3Y1'
    for k,hi in INTS.items():out+=number(p[k],1 if k.endswith('_divisor')else 0,hi)
    if p['primary']==p['secondary']or max(p['primary'],p['secondary'])>=len(gear['slots']):raise ValueError('stats hand slots')
    for k,hi in FLOATS.items():out+=real(p[k],hi)
    for k in POLYS:
        v=p[k]
        if not isinstance(v,dict)or set(v)!={'coefficient','linear','divisor','base','attribute','offset'}:raise ValueError('stats polynomial')
        out+=real(v['coefficient'],1)+real(v['linear'],1,k=='health')+number(v['divisor'],1,100)+number(v['base'],0,10000)+number(v['attribute'],0,4)+number(v['offset'],0,255)
    if p['mana']['coefficient']==0 and p['stamina_resource']['coefficient']==0:raise ValueError('resource polynomial missing')
    cats=p['categories'];ids=set()
    if not isinstance(cats,list)or not 1<=len(cats)<=32:raise ValueError('stats categories')
    out+=u(len(cats))
    for c in cats:
        if not isinstance(c,dict)or set(c)!={'id','coefficient','dexterity','offhand'}or c['id']in ids or not re.fullmatch(re.escape(game)+r':[a-z][a-z0-9_/-]{0,95}',c['id']):raise ValueError('stats category')
        ids.add(c['id']);out+=string(c['id'])+real(c['coefficient'],1)+number(c['dexterity'],0,1)+number(c['offhand'],0,2)
    items=p['items'];seen=set();defs={i['id']for i in gear['items']}
    if not isinstance(items,list)or len(items)!=len(defs):raise ValueError('stats coverage')
    out+=u(len(items))
    for i in items:
        if not isinstance(i,dict)or set(i)!=set(BONUSES)|{'id','category','attributes'}or i['id']not in defs or i['id']in seen or i['category']not in ids:raise ValueError('stats item')
        seen.add(i['id']);out+=string(i['id'])+string(i['category'])
        for k,hi in BONUSES.items():out+=number(i[k],0,hi)
        if not isinstance(i['attributes'],list)or len(i['attributes'])!=5:raise ValueError('stats attributes')
        out+=b''.join(number(v,0,255)for v in i['attributes'])
    return out
