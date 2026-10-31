"""Package-owned fixed merchant prices, carrying weights and service locations."""
import math,re
from common import u,f,string

def cook(p,game,bag,reward):
    if not isinstance(p,dict) or set(p)!={'weight_limit','max_quantity','bulk_price','bulk_quantity','items','shops'}: raise ValueError('commerce vocabulary')
    def number(v,lo,hi):
        if type(v) is not int or not lo<=v<=hi: raise ValueError('commerce bound')
        return u(v)
    def ident(v):
        if not isinstance(v,str) or not re.fullmatch(re.escape(game)+r':[a-z][a-z0-9_/-]{0,95}',v): raise ValueError('commerce identity')
        return string(v)
    b=b'N3O1'+number(p['weight_limit'],1,2**31-1)+number(p['max_quantity'],1,9999)+number(p['bulk_price'],0,2**31-1)+number(p['bulk_quantity'],1,p['max_quantity'])
    items=p['items'];definitions={i['id']:i for i in bag['items']}
    if not isinstance(items,list) or len(items)!=len(definitions): raise ValueError('commerce item coverage')
    seen=set();b+=u(len(items))
    for i in items:
        if not isinstance(i,dict) or set(i)!={'id','weight','price','sell_divisor'} or i['id'] in seen or i['id'] not in definitions: raise ValueError('commerce item')
        seen.add(i['id']);b+=ident(i['id'])+number(i['weight'],0,1000000)+number(i['price'],1,2**31-1)+number(i['sell_divisor'],1,10000)
    shops=p['shops']
    if not isinstance(shops,list) or not 1<=len(shops)<=64: raise ValueError('shop count')
    seen=set();b+=u(len(shops))
    for shop in shops:
        if not isinstance(shop,dict) or set(shop)!={'id','label','position','radius','remote_sell','items'} or shop['id'] in seen: raise ValueError('shop vocabulary')
        seen.add(shop['id']);label=shop['label'];pos=shop['position'];radius=shop['radius'];offers=shop['items']
        if not isinstance(label,str) or not 1<=len(label)<=64 or any(not 32<=ord(c)<=126 for c in label): raise ValueError('shop label')
        if not isinstance(pos,list) or len(pos)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1000 for v in pos): raise ValueError('shop position')
        if type(radius) not in (int,float) or not math.isfinite(radius) or not .5<=radius<=20 or type(shop['remote_sell']) is not bool: raise ValueError('shop access')
        if not isinstance(offers,list) or not 1<=len(offers)<=64 or len(set(offers))!=len(offers) or any(i not in definitions or i==reward for i in offers): raise ValueError('shop offers')
        b+=ident(shop['id'])+string(label)+f(pos)+f([radius])+u(int(shop['remote_sell']))+u(len(offers))+b''.join(ident(i) for i in offers)
    return b
