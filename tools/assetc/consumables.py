"""Bounded ordinary recovery items; values and timing belong to the package."""
from common import u

def cook(rows,inventory):
    items=inventory['items']; indexes={v['id']:i+1 for i,v in enumerate(items)}
    if not isinstance(rows,list) or not 1<=len(rows)<=64:raise ValueError('consumable count')
    result=b'N3X1'+u(len(rows));seen=set()
    for row in rows:
        if set(row)!={'item','health','resource','delay_ms','cooldown_ms'}:raise ValueError('consumable fields')
        name=row['item'];values=[row[k] for k in ('health','resource','delay_ms','cooldown_ms')]
        if name not in indexes or name in seen or any(type(v)is not int for v in values):raise ValueError('consumable item')
        hp,mp,delay,cooldown=values
        if not 0<=hp<=100000 or not 0<=mp<=100000 or not hp+mp or not 0<=delay<=2000 or not 50<=cooldown<=60000 or items[indexes[name]-1]['durability']:raise ValueError('consumable bounds')
        seen.add(name);result+=u(indexes[name])+b''.join(u(v)for v in values)
    return result
