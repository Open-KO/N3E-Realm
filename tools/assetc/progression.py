"""Original, bounded N3P1 contribution/claim definition; no authentic table claim."""
import math
import re
import struct
from common import u, f, string


def cook(p, gameplay, game):
    keys = {'model', 'stat_policy', 'curve', 'item', 'origin', 'author', 'revision',
            'thresholds', 'capacity', 'starting', 'npc_level', 'base_xp', 'radius', 'claim_radius', 'ttl'}
    items = isinstance(p,dict) and p.get('model') == 'contribution_items_v5'
    if items: keys.add('items')
    coins = isinstance(p,dict) and p.get('model') in ('contribution_drops_v4','contribution_items_v5')
    loot = isinstance(p,dict) and p.get('model') in ('contribution_party_loot_v3','contribution_drops_v4','contribution_items_v5')
    if coins: keys.add('coins')
    party = isinstance(p,dict) and p.get('model') in ('contribution_party_v2','contribution_party_loot_v3','contribution_drops_v4','contribution_items_v5')
    if loot: keys.add('party_loot')
    if party: keys.add('party_rewards')
    if not isinstance(p, dict) or set(p) != keys or p['model'] not in ('contribution_claim_v1','contribution_party_v2','contribution_party_loot_v3','contribution_drops_v4','contribution_items_v5') or p['stat_policy'] not in ('fixed_v1','equipment_v1'):
        raise ValueError('progression vocabulary')
    for key in ('curve', 'item'):
        if not isinstance(p[key], str) or not re.fullmatch(re.escape(game) + r':[a-z][a-z0-9_/-]{0,95}', p[key]):
            raise ValueError('progression ID')
    if p['origin'] != 'original synthetic' or not isinstance(p['author'], str) or not 1 <= len(p['author'].encode()) <= 200:
        raise ValueError('progression provenance')
    for key, lo, hi in [('revision', 1, 2**32-1), ('capacity', 1, 64), ('starting', 0, 64), ('npc_level', 1, 10), ('base_xp', 1, 1000000), ('ttl', 10, 600)]:
        if type(p[key]) is not int or not lo <= p[key] <= hi:
            raise ValueError('progression ' + key)
    for key, lo, hi in [('radius', 1, 100), ('claim_radius', .5, 10)]:
        if type(p[key]) not in (int, float) or not math.isfinite(p[key]) or not lo <= p[key] <= hi:
            raise ValueError('progression ' + key)
    t = p['thresholds']
    if not isinstance(t, list) or len(t) != 10 or any(type(x) is not int or not 0 <= x < 2**63 for x in t) or t[0] != 0 or any(a >= b for a,b in zip(t,t[1:])):
        raise ValueError('progression thresholds')
    if (p['item'], p['capacity'], p['starting']) != (gameplay['item'], gameplay['slots'], gameplay['starting_items']):
        raise ValueError('progression inventory mismatch')
    extra = b''
    if party:
        r = p['party_rewards']
        if not isinstance(r,dict) or set(r) != {'bonus_tenths','level_minimum','level_maximum','level_gap','level_xp'}: raise ValueError('party reward vocabulary')
        for k,lo,hi in [('bonus_tenths',0,8),('level_gap',0,100)]:
            if type(r[k]) is not int or not lo<=r[k]<=hi: raise ValueError('party reward '+k)
        for k,lo,hi in [('level_minimum',0,1),('level_maximum',1,10)]:
            if type(r[k]) not in (int,float) or not math.isfinite(r[k]) or not lo<=r[k]<=hi: raise ValueError('party reward '+k)
        xp=r['level_xp']
        if not isinstance(xp,list) or len(xp)!=10 or any(type(v) is not int or not 1<=v<=2**31-1 for v in xp) or xp[:9]!=[b-a for a,b in zip(t,t[1:])]: raise ValueError('party reward level table')
        if p['radius'] != int(p['radius']): raise ValueError('party reward integer radius')
        extra=u(r['bonus_tenths'])+struct.pack('<dd',r['level_minimum'],r['level_maximum'])+u(r['level_gap'])+struct.pack('<10I',*xp)
    if loot:
        r=p['party_loot']
        if not isinstance(r,dict) or set(r)!={'radius'} or type(r['radius']) is not int or not 1<=r['radius']<=100: raise ValueError('party loot radius')
        extra+=u(r['radius'])
    if coins:
        c=p['coins'];fields=['base','minimum_percent','maximum_percent','event_percent','party_bonus_percent','maximum','overflow','pickup_bonus_percent','bonus_cap']
        if not isinstance(c,dict) or set(c)!=set(fields+['currency']):raise ValueError('coin drop vocabulary')
        if not isinstance(c['currency'],str) or not re.fullmatch(re.escape(game)+r':[a-z][a-z0-9_/-]{0,95}',c['currency']):raise ValueError('coin currency ID')
        bounds=[(0,(2**31-1)//100),(0,100),(0,100),(0,32767),(0,100),(1,32766),(1,32766),(0,100),(1,32766)]
        for k,(lo,hi) in zip(fields,bounds):
            if type(c[k]) is not int or not lo<=c[k]<=hi:raise ValueError('coin drop '+k)
        if c['minimum_percent']>c['maximum_percent'] or c['overflow']>c['maximum'] or c['base']*(1+c['event_percent']*.01)*(1+7*(c['party_bonus_percent']/100))>2**31-1:raise ValueError('coin generation bounds')
        extra+=string(c['currency'])+b''.join(u(c[k])for k in fields)
    if items:
        import item_drops
        extra+=item_drops.cook(p['items'],game)
    return ((b'N3P5' if items else b'N3P4' if coins else b'N3P3' if loot else b'N3P2' if party else b'N3P1') + u(1) + u(2 if p['stat_policy']=='equipment_v1' else 1) + b''.join(string(p[k]) for k in ('curve','item','origin','author'))
            + u(p['revision']) + struct.pack('<10Q', *t)
            + b''.join(u(p[k]) for k in ('capacity','starting','npc_level','base_xp'))
            + f([p['radius'], p['claim_radius']]) + u(p['ttl']) + extra)
