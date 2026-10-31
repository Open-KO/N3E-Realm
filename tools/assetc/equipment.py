"""Named equipment slots and base-attribute requirements, independent of game IDs."""
from common import u,string

def cook(p,bag,game):
    if not isinstance(p,dict) or set(p)!={'race','title','attributes','slots','items'}:raise ValueError('equipment vocabulary')
    def number(v,hi=255):
        if type(v) is not int or not 0<=v<=hi:raise ValueError('equipment number')
        return u(v)
    def attrs(a):
        if not isinstance(a,list) or len(a)!=5:raise ValueError('equipment attributes')
        return b''.join(number(v) for v in a)
    slots=p['slots']
    if not isinstance(slots,list) or not 1<=len(slots)<=16 or len(set(slots))!=len(slots) or any(not isinstance(s,str) or not 1<=len(s)<=32 or any(not 32<=ord(c)<=126 for c in s) for s in slots):raise ValueError('equipment slots')
    out=b'N3Q1'+number(p['race'])+number(p['title'])+attrs(p['attributes'])+u(len(slots))+b''.join(string(s) for s in slots)
    items=p['items'];defs={i['id']:i for i in bag['items']}
    if not isinstance(items,list) or not 1<=len(items)<=64:raise ValueError('equipment items')
    out+=u(len(items));seen=set()
    def indices(a,empty):
        if not isinstance(a,list) or (not empty and not a) or len(set(a))!=len(a) or any(type(v)is not int or not 0<=v<len(slots) for v in a):raise ValueError('equipment slot mask')
        return u(sum(1<<v for v in a))
    for i in items:
        if not isinstance(i,dict) or set(i)!={'id','slots','blocks','title','race','attributes','swappable'}:raise ValueError('equipment item vocabulary')
        if i['id'] not in defs or i['id'] in seen or defs[i['id']]['stack_limit']!=1:raise ValueError('equipment item')
        seen.add(i['id'])
        if set(i['slots'])&set(i['blocks']):raise ValueError('equipment self blocking')
        if type(i['swappable'])is not bool:raise ValueError('equipment swap flag')
        out+=string(i['id'])+indices(i['slots'],False)+indices(i['blocks'],True)+number(i['title'])+number(i['race'])+attrs(i['attributes'])+u(i['swappable'])
    return out
