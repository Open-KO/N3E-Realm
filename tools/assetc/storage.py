"""Account storage policy. Services own local access and open fees."""
import re
from common import u,f,string

def cook(p,game):
    if not isinstance(p,dict) or set(p)!={'capacity','coin_limit','services'}:raise ValueError('storage vocabulary')
    def integer(v,lo,hi):
        if type(v)is not int or not lo<=v<=hi:raise ValueError('storage integer')
        return u(v)
    out=b'N3B1'+integer(p['capacity'],1,192)+integer(p['coin_limit'],1,2100000000)
    services=p['services'];seen=set()
    if not isinstance(services,list)or not 1<=len(services)<=64:raise ValueError('storage services')
    out+=u(len(services))
    for s in services:
        if not isinstance(s,dict)or set(s)!={'id','label','position','radius','remote','open_fee'}:raise ValueError('storage service vocabulary')
        ident=s['id']
        if not isinstance(ident,str)or not re.fullmatch(re.escape(game)+r':[a-z][a-z0-9_/-]{0,95}',ident):raise ValueError('storage identity')
        if ident in seen:raise ValueError('duplicate storage service')
        seen.add(ident);label=s['label']
        if not isinstance(label,str)or not 1<=len(label)<=64 or any(not 32<=ord(c)<=126 for c in label):raise ValueError('storage label')
        pos=s['position']
        if not isinstance(pos,list)or len(pos)!=3 or any(type(v)not in(int,float)or abs(v)>1000 for v in pos):raise ValueError('storage position')
        if type(s['radius'])not in(int,float)or not .5<=s['radius']<=20 or type(s['remote'])is not bool:raise ValueError('storage access')
        out+=string(ident)+string(label)+f(pos)+f([s['radius']])+u(int(s['remote']))+integer(s['open_fee'],0,2100000000)
    return out
