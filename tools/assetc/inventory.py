"""Versioned generic item definitions and initial bag policy."""
import re
from common import u, string


def cook(p, game, reward, starting=0):
    if not isinstance(p, dict) or set(p) != {'capacity','currency','currency_limit','starting_currency','items'}:
        raise ValueError('inventory vocabulary')
    def number(v, lo, hi):
        if type(v) is not int or not lo <= v <= hi:
            raise ValueError('inventory bounds')
        return u(v)
    def identity(v):
        if not isinstance(v,str) or not re.fullmatch(re.escape(game)+r':[a-z][a-z0-9_/-]{0,95}',v):
            raise ValueError('inventory namespace')
        return string(v)
    result = b'N3I1'+number(p['capacity'],1,64)+identity(p['currency'])
    result += number(p['currency_limit'],1,2**31-1)+number(p['starting_currency'],0,p['currency_limit'])
    items=p['items']
    if not isinstance(items,list) or not 1 <= len(items) <= 64:
        raise ValueError('inventory definition count')
    seen=set(); initial=0; found=False
    result += u(len(items))
    for item in items:
        if not isinstance(item,dict) or set(item)!={'id','label','stack_limit','durability','starting'}:
            raise ValueError('item vocabulary')
        if item['id'] in seen: raise ValueError('duplicate item')
        seen.add(item['id'])
        label=item['label']
        if not isinstance(label,str) or not 1<=len(label)<=64 or any(not 32<=ord(c)<=126 for c in label):
            raise ValueError('item label')
        result += identity(item['id'])+string(label)+number(item['stack_limit'],1,9999)+number(item['durability'],0,65535)+number(item['starting'],0,item['stack_limit'])
        initial += item['starting']>0
        if item['id']==reward:
            found=True
            if item['stack_limit']!=1 or item['starting']!=0 or item['durability']!=0: raise ValueError('legacy reward item must be singleton with progression-owned starting quantity')
    if not found or initial>=p['capacity'] or initial+starting>p['capacity']: raise ValueError('reward item/capacity')
    return result
