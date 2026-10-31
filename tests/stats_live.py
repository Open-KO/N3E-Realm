"""Original equipment-derived stat fixture and live authority checks."""
import json,shutil,sys,time,struct
from pathlib import Path
from world_peer import Budget,fields,first,integer,blob
from isolation import once_per_run

@once_per_run
def prepare():
    from equipment_live import prepare as gear_prepare
    gear_prepare();root=Path('build/ko-completion/stats/source');root.mkdir(parents=True,exist_ok=True)
    shutil.copytree('build/ko-completion/equipment/source',root,dirs_exist_ok=True)
    m=json.loads((root/'package.json').read_text());m['engine_version']=19;m['protocol_version']=12
    m['progression']['stat_policy']='equipment_v1'
    m['progression']['thresholds'][1]=10
    m['gameplay']['npc_health']=10
    m['damage']['npc']['attack']=3
    poly=lambda coefficient,linear,base,attribute,offset:dict(coefficient=coefficient,linear=linear,base=base,attribute=attribute,offset=offset,divisor=5)
    p=dict(primary=0,secondary=1,dual_wield=1,dexterity_attack=0,weapon_floor=3,attack_base=3,attack_offset=40,broken_weapon_divisor=10,broken_raw_divisor=2,strength_threshold=150,stamina_threshold=100,weight_scale=1,rate_initial=100,
      secondary_scale=.5,attack_linear=.005,defense_coefficient=1,accuracy_coefficient=.01,evasion_coefficient=.01,strength_attack=1,stamina_defense=1,rate_scale=.01,rate_base=1,
      health=poly(.0015,.1,20,1,0),mana=poly(0,.2,20,3,30),stamina_resource=poly(.0015,.1,0,1,0),
      categories=[dict(id='demo:weapon/sword',coefficient=.00013,dexterity=0,offhand=0),dict(id='demo:weapon/dagger',coefficient=.0001,dexterity=1,offhand=1),dict(id='demo:weapon/bow',coefficient=.0002,dexterity=1,offhand=2),dict(id='demo:weapon/none',coefficient=0,dexterity=0,offhand=0)],items=[])
    for i in m['equipment']['items']:
        p['items'].append(dict(id=i['id'],category='demo:weapon/sword' if i['id'].endswith(('blade','twohand'))else 'demo:weapon/none',attack=40 if i['id'].endswith(('blade','twohand'))else 0,defense=12 if i['id'].endswith('shield')else 0,health=50 if i['id'].endswith('ring')else 0,resource=20 if i['id'].endswith('ring')else 0,accuracy=10 if i['id'].endswith('ring')else 0,evasion=5 if i['id'].endswith('ring')else 0,attributes=[0,10,0,0,0]if i['id'].endswith('ring')else [0]*5))
    m['stats']=p
    (root/'package.json').write_text(json.dumps(m));sys.path.insert(0,str(Path('tools/assetc').resolve()));import main
    package=Path('build/ko-completion/stats/package');main.cook(root,package);return package.resolve()

# Independent high-precision arithmetic, rounding input float32 coefficients exactly.
def oracle(m,records,level):
    from decimal import Decimal,localcontext
    D=Decimal
    def F(v):return D.from_float(struct.unpack('<f',struct.pack('<f',v))[0])
    with localcontext() as ctx:
        ctx.prec=60;p=m['stats'];gear=m['equipment'];base=gear['attributes'];attrs=base[:];defs={i['id']:i for i in p['items']};cats={i['id']:i for i in p['categories']};atk=ac=hp=mp=0;hit=eva=p['rate_initial']
        for slot,record in enumerate(records):
            if not record:continue
            i=defs[record[0]];damage=i['attack'] if record[1] else i['attack']//p['broken_weapon_divisor']
            if slot==p['primary']:atk+=damage
            if slot==p['secondary']and p['dual_wield']:atk=int(D(atk)+D(damage)*F(p['secondary_scale']))
            hp+=i['health'];mp+=i['resource']
            if record[1]:
                ac+=i['defense'];hit+=i['accuracy'];eva+=i['evasion'];attrs=[a+b for a,b in zip(attrs,i['attributes'])]
        atk=max(atk,p['weapon_floor']);right=records[p['primary']];left=records[p['secondary']];raw=0;coef=D(0);dex=False
        if right:
            i=defs[right[0]];c=cats[i['category']];raw=i['attack'];coef=F(c['coefficient']);dex=c['dexterity']
        if left and(coef==0 or dex):
            i=defs[left[0]];c=cats[i['category']]
            if c['offhand']:
                raw+=int(D(i['attack'])*F(p['secondary_scale']))if c['offhand']==1 else i['attack'];coef=F(c['coefficient']);dex=True
        precise=dex or p['dexterity_attack'];a=attrs[2 if precise else 0];w=raw if precise else atk
        attack=int(D(level*a*w)*coef+D((a+p['attack_offset'])*w)*F(p['attack_linear'])+p['attack_base'])
        if precise:
            if(dex and not(right and right[1])and not(left and left[1]))or(not dex and right and not right[1]):attack//=p['broken_raw_divisor']
        else:attack+=int(D(max(base[0]-p['strength_threshold'],0))*F(p['strength_attack']))
        defense=int(D(level+ac)*F(p['defense_coefficient']))+int(D(max(base[1]-p['stamina_threshold'],0))*F(p['stamina_defense']))
        def poly(name):
            q=p[name];a=attrs[q['attribute']]+q['offset'];linear=D.from_float(float(q['linear']))if name=='health'else F(q['linear'])
            return int(D(a*level*level)*F(q['coefficient'])+D(level*a)*linear+a//q['divisor'])+q['base']
        health=poly('health')+hp;resource=poly('mana'if p['mana']['coefficient']else 'stamina_resource')+mp
        rate=lambda name,bonus:struct.unpack('<f',struct.pack('<f',float((D(level*attrs[2])*F(p[name])+F(p['rate_base']))*bonus*F(p['rate_scale']))))[0]
        return dict(attack=attack,defense=defense,accuracy=rate('accuracy_coefficient',hit),evasion=rate('evasion_coefficient',eva),max_health=health,max_resource=resource,carry_limit=(attrs[0]+level)*p['weight_scale'],attributes=attrs)

def decode_stats(s):
    # Five packed u32 attributes; reuse the generic protobuf decoder's varint parser.
    packed=first(s,8,b'');attrs=[];value=shift=0
    for b in packed:
        value|=(b&127)<<shift
        if b<128:attrs.append(value);value=shift=0
        else:shift+=7
    return dict(zip(['attack','defense','accuracy','evasion','max_health','max_resource','carry_limit'],[first(s,i)for i in range(1,8)]),attributes=attrs)

def audit(connect,restart,sql):
    m=json.loads(Path('build/ko-completion/stats/source/package.json').read_text());p=connect('explorer');requests=0
    def req(q=b'',status=b'ok'):
        nonlocal requests
        requests+=1
        if requests%7==0:p.pump(1.05)
        p.send(32,q);tag,r=p.until(33,4);assert tag==33 and first(r,2)==status,(tag,r,status)
        return r,fields(first(r,3))
    def tx(name,state,op,src,dst):
        records=state[6]if op in(6,7)else state[5]
        return integer(1,op)+blob(2,name)+integer(3,first(state,1))+integer(4,src)+integer(5,dst)+integer(6,first(fields(records[src]),1))
    def world(state,level=1):
        records=[(first(fields(s),2).decode(),first(fields(s),4))if fields(s)else None for s in state[6]];want=oracle(m,records,level)
        end=time.monotonic()+3
        while time.monotonic()<end:
            _,w=p.until(10);got=decode_stats(fields(first(w,13,b'')))
            if got==want and first(fields(first(w,13)),9)==first(state,1):
                assert first(w,8)==want['max_health']and first(w,9)==want['max_resource'];return w
        raise AssertionError((got,want))
    _,s=req();w=world(s);initial_hp=first(p.entities[p.id],7)
    blade=tx('stats-blade',s,5,0,0);original,s=req(blade,b'committed');world(s)
    ring=tx('stats-ring',s,5,4,2);_,s=req(ring,b'committed');w=world(s)
    # Max increases without healing; no NPC can reach the origin in this fixture.
    assert first(p.entities[p.id],7)==initial_hp,(p.entities[p.id],initial_hp)
    assert first(w,8)>initial_hp
    saved=s;p.logout();p=connect('explorer');world(saved)
    assert first(p.entities[p.id],7)==first(w,8)
    _,s=req(tx('stats-unring',s,6,2,4),b'committed');w=world(s)
    assert first(p.entities[p.id],7)==first(w,8)==initial_hp
    replay,_=req(blade,b'committed');assert replay==original;world(s) # old bag snapshot must not replace newer gear
    # Current computed carry 61 admits a purchase rejected by fixed commerce cap 36.
    buy=integer(1,2)+blob(2,'stats-carry')+integer(3,first(s,1))+integer(4,9)+blob(7,'demo:shop/supplies')+blob(8,'demo:item/potion')+integer(9,1)
    _,s=req(buy,b'committed');assert first(s,4)==87
    # Hard restart with broken gear verifies persistent durability -> restored derived stats.
    from repair_live import encode,damage
    import copy
    broken=copy.deepcopy(s);broken[1]=[first(s,1)+1];item=fields(broken[6][0]);item.pop(4,None);broken[6][0]=encode(item)
    p.logout();sql("UPDATE character_bags b SET state=decode('"+encode(broken).hex()+"','hex') FROM characters c WHERE b.character_id=c.id AND c.name='Explorer'")
    restart();p=connect('explorer');_,s=req();assert s==broken;w=world(s);broken_attack=first(fields(first(w,13)),1)
    repair=integer(1,8)+blob(2,'stats-repair')+integer(3,first(s,1))+integer(6,first(fields(s[6][0]),1))+blob(8,'demo:item/blade')
    repaired,s=req(repair,b'committed');w=world(s);assert first(fields(first(w,13)),1)>broken_attack
    # Observe a real melee hit; the retained fixed attack 36 has a disjoint damage range.
    _,s=req(tx('combat-ring',s,5,4,2),b'committed');world(s);p.logout();p=connect('explorer');world(s)
    # Hit rolls decide when the first hit lands: derived accuracy 1.76 against the
    # sentinel's evasion 100 hits half the strikes, so the fight is bounded by 30
    # resolved strikes (a spurious failure 2**-30), not by time (PQ-123; 12 s left
    # about 6 strikes, failing one run in 64). Sentinel hits deal 1 (attack 3)
    # once a second, against the explorer's 92 health, inside the 80 s guard.
    fight=Budget('no derived melee hit',strikes=30,guard=80);hit=False
    while not hit and fight.ok(p.entities):
        p.pump(.06)
        me=p.entities[p.id];assert first(me,7)>0,('explorer died before a hit',fight.last,p.entities)
        npcs=[e for e in p.entities.values()if first(e,9)==1 and first(e,7)>0]
        if not npcs:continue
        npc=min(npcs,key=lambda e:(first(e,3)-first(me,3))**2+(first(e,5)-first(me,5))**2)
        distance=(first(npc,3)-first(me,3))**2+(first(npc,5)-first(me,5))**2
        if distance<1:
            p.move(0,0);p.action_seq+=1;p.send(15,integer(1,p.session)+integer(2,p.action_seq)+integer(3,first(npc,1))+blob(4,p.action_id));_,result=p.until(16);fight.result(first(result,2),p.entities);me={15:[first(result,4)]}
            # The action result records damage in field 4; snapshot strike field 15.
            if first(me,15)>0:
                expected=oracle(m,[(first(fields(x),2).decode(),first(fields(x),4))if fields(x)else None for x in s[6]],1)
                base=expected['attack']*200//(m['damage']['npc']['defense']+240)
                assert int(struct.unpack('<f',struct.pack('<f',.85))[0]*base)<=first(me,15)<=int((struct.unpack('<f',struct.pack('<f',.85))[0]+struct.unpack('<f',struct.pack('<f',.3))[0])*base),(me,expected)
                hit=True
        else:
            fight.step(p.entities);scale=max(1,distance**.5);p.move((first(npc,3)-first(me,3))/scale,(first(npc,5)-first(me,5))/scale)
    # A real durable kill settlement crosses the original fixture's first threshold.
    world(s,2);assert first(p.inventory,5)==2,p.inventory
    p.logout();sql("UPDATE character_reward_progress r SET curve_xp=140,revision=revision+1 FROM characters c WHERE r.character_id=c.id AND c.name='Explorer'")
    restart();p=connect('explorer');_,saved=req();assert saved==s;world(s,5)
    replay,_=req(repair,b'committed');assert replay==repaired;world(s,5);p.logout()
    # Companion is reserved for the native equipment/repair input replay.
    p=connect('companion');_,other=req();p.logout();damage(sql,'Companion',other)
    print('PASS derived stats, no gear healing, HP clamp, old retry monotonicity, computed carry, broken gear/repair, real melee, durable level growth and hard restart',flush=True)
