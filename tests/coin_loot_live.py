"""Original generated-coin fixtures and real TLS verification."""
import json,shutil,sys
from pathlib import Path
from isolation import once_per_run

@once_per_run
def prepare(alternate=False,ttl=600,full=False):
    from party_loot_live import prepare as base
    source=base(full=full,ttl=ttl).parent/'source'
    root=Path('build/ko-completion/coin-loot')/('full' if full else 'alternate' if alternate else 'base')/'source'
    root.mkdir(parents=True,exist_ok=True);shutil.copytree(source,root,dirs_exist_ok=True)
    m=json.loads((root/'package.json').read_text());m['engine_version']=27;m['protocol_version']=20
    p=m['progression'];p['model']='contribution_drops_v4'
    if not full:
        m['inventory']={'capacity':8,'currency':'demo:currency/coin','currency_limit':2100000000,'starting_currency':1000,
            'items':[{'id':p['item'],'label':'Token','stack_limit':1,'durability':0,'starting':0}]}
    m['inventory']['currency_limit']=2100000000;m['inventory']['starting_currency']=1000
    p['coins']={'currency':m['inventory']['currency'],'base':1000,'minimum_percent':70,'maximum_percent':100,
        'event_percent':10 if alternate else 0,'party_bonus_percent':20,'maximum':32766,'overflow':32000,
        'pickup_bonus_percent':30,'bonus_cap':32700}
    (root/'package.json').write_text(json.dumps(m));sys.path.insert(0,str(Path('tools/assetc').resolve()));import main
    out=root.parent/'package';main.cook(root,out)
    for name in ['old','next']:
        other=root.parent/name/'source';shutil.copytree(root,other,dirs_exist_ok=True)
        variant=json.loads(json.dumps(m))
        if name=='old':
            variant['engine_version']=26;variant['protocol_version']=19
            variant['progression']['model']='contribution_party_loot_v3';del variant['progression']['coins']
        else:variant['progression']['coins']['base']=1001
        (other/'package.json').write_text(json.dumps(variant));main.cook(other,other.parent/'package')
    return out.resolve()

def audit(connect,restart,sql):
    import time
    from world_peer import DISCONNECTED,Budget,first,fields,integer,blob
    peers=[];pings={};claim_seq={};party_seq={}
    def heartbeat():
        now=time.monotonic()
        for p in peers:
            if now-pings.get(p,0)>.5:p.send(14);pings[p]=now
    def wait(p,tag,predicate=lambda _:True):
        deadline=time.monotonic()+6
        while time.monotonic()<deadline:
            heartbeat();t,d=p.receive();assert t!=4,(t,d)
            if t==tag and predicate(d):return d
        raise AssertionError(('timeout',tag,p.inventory))
    def command(p,op=0,name='',token=0):
        party_seq[p]=party_seq.get(p,0)+1
        p.send(42,integer(1,party_seq[p])+integer(2,op)+blob(3,name)+integer(4,token))
        return first(wait(p,44),2)
    def drops(p):p.send(23);return [fields(v)for v in wait(p,24).get(1,[])]
    def claim(p,d):
        claim_seq[p]=claim_seq.get(p,0)+1
        p.send(25,integer(1,p.session)+integer(2,claim_seq[p])+integer(3,p.id)+integer(4,first(d,1))+integer(5,first(d,2))+blob(6,first(d,3))+integer(7,first(d,9) or 1))
        return wait(p,26,lambda result:first(result,1)==first(d,1) and first(result,2)!=b'pending')
    def walk(p,goal):
        deadline=time.monotonic()+20;last=0
        while time.monotonic()<deadline:
            wait(p,10)
            if time.monotonic()-last<.12:continue
            last=time.monotonic();me=p.entities[p.id]
            dx,dz=goal[0]-first(me,3),goal[1]-first(me,5);distance=(dx*dx+dz*dz)**.5
            if distance<.5:p.move(0,0);p.pump(.15);return
            p.move(dx/max(1,distance),dz/max(1,distance))
        raise AssertionError('walk timeout')
    def kill(p):
        # Strikes hit 80 % (contested_melee_v1 accuracy 50 against evasion 100) and a
        # kill takes three: bounded by 20 resolved strikes (a spurious failure about
        # 3e-11), not by time; the 90 s guard only catches a stall (PQ-123).
        previous=first(p.inventory,4);fight=Budget('kill',strikes=20,guard=90);last=0
        while fight.ok(p.inventory,p.entities):
            wait(p,10)
            if first(p.inventory,4)>previous:return
            if time.monotonic()-last<.12:continue
            last=time.monotonic();me=p.entities[p.id]
            assert first(me,7)>0,('player died during the kill',fight.last,p.entities)
            npcs=[e for e in p.entities.values()if first(e,9)==1 and first(e,7)>0]
            if not npcs:continue
            npc=min(npcs,key=lambda e:(first(e,3)-first(me,3))**2+(first(e,5)-first(me,5))**2)
            dx,dz=first(npc,3)-first(me,3),first(npc,5)-first(me,5);distance=(dx*dx+dz*dz)**.5
            if distance<.9:p.move(0,0);fight.result(p.action(first(npc,1)))
            else:fight.step();p.move(dx/max(1,distance),dz/max(1,distance))
    def bag(p):
        p.send(32);result=wait(p,33);return fields(first(result,3))
    def coins(result):return [fields(row)for row in result.get(7,[])]
    a=connect('explorer');peers.append(a);b=connect('companion');peers.append(b)
    start_a=first(bag(a),4);start_b=first(bag(b),4)
    assert command(a,1,'Companion')==b'invited'
    invitation=wait(b,43,lambda d:first(d,5)>0)
    assert command(b,2,token=first(invitation,5))==b'joined'
    wait(b,43,lambda d:len(d.get(4,[]))==2)
    kill(a);all_drops=drops(a);assert len(all_drops)==2,all_drops
    drop=next(d for d in all_drops if first(d,10)==1);item=next(d for d in all_drops if first(d,10)==0)
    amount=first(drop,9);assert 840<=amount<=1200,amount
    c=connect('bystander');peers.append(c);assert not drops(c)
    assert first(claim(c,drop),2)==b'unknown';c.logout();peers.remove(c)
    result=claim(a,drop);assert first(result,2)==b'claimed',result
    shares=coins(result);assert len(shares)==2 and all(first(s,3)==amount//2 for s in shares),result
    notice=wait(b,26,lambda d:first(d,1)==first(drop,1));assert notice==result
    assert first(bag(a),4)==start_a+amount//2
    assert first(bag(b),4)==start_b+amount//2
    assert claim(b,drop)==result
    # Item and currency from the same encounter are independently claimable.
    token=claim(a,item);assert first(token,2)==b'claimed' and first(token,6)==b'Explorer',token
    assert sql('SELECT count(*) FROM loot_claim_results WHERE encounter='+str(first(drop,2))).strip()=='2'
    kill(a);second=next(d for d in drops(a)if first(d,10)==1)
    assert command(b,4)==b'disbanded';walk(b,(first(second,5),first(second,7)))
    solo=claim(b,second);assert len(coins(solo))==1 and first(coins(solo)[0],4)==first(second,9),solo
    expected=sql("SELECT character_id,encode(state,'hex') FROM character_bags ORDER BY character_id")
    for p in peers:p.logout()
    peers.clear();restart()
    assert sql("SELECT character_id,encode(state,'hex') FROM character_bags ORDER BY character_id")==expected
    b=connect('companion');peers.append(b);b.send(27,integer(1,first(second,1)));assert wait(b,26)==solo
    assert first(bag(b),4)==start_b+amount//2+first(second,9)
    b.logout();peers.clear()
    restart(claim_fault='before_apply')
    a=connect('explorer');peers.append(a);b=connect('companion');peers.append(b)
    before_a=first(bag(a),4);before_b=first(bag(b),4)
    assert command(a,1,'Companion')==b'invited'
    invitation=wait(b,43,lambda d:first(d,5)>0)
    assert command(b,2,token=first(invitation,5))==b'joined'
    wait(b,43,lambda d:len(d.get(4,[]))==2)
    kill(a);crash_drop=next(d for d in drops(a)if first(d,10)==1)
    try:claim(a,crash_drop)
    except DISCONNECTED:pass  # not a timeout (PQ-126)
    else:raise AssertionError('before-apply coin crash did not exit')
    for peer in peers:peer.s.close()
    peers.clear();restart(expected_exit=86)
    a=connect('explorer');peers.append(a);b=connect('companion');peers.append(b)
    b.send(27,integer(1,first(crash_drop,1)));recovered=wait(b,26)
    assert first(recovered,2)==b'claimed' and len(coins(recovered))==2,recovered
    paid={first(v,2):first(v,4)for v in coins(recovered)}
    assert first(bag(a),4)==before_a+paid[b'Explorer']
    assert first(bag(b),4)==before_b+paid[b'Companion']
    assert claim(a,crash_drop)==recovered
    assert first(bag(a),4)==before_a+paid[b'Explorer']
    for peer in peers:peer.logout()
    peers.clear()
    print('PASS real generated coin/item drops, private audience, current-party wallet shares, recipient notices, leave-before-pickup, independent same-encounter claims and immutable restart/before-apply crash recovery',flush=True)

def graphical_claim(p):
    """The native party leader receives the observer's real pickup while its UI waits."""
    import time
    from world_peer import first,fields,integer,blob
    deadline=time.monotonic()+25;last=ping=0;previous=first(p.inventory,4)
    while time.monotonic()<deadline:
        now=time.monotonic()
        if now>=ping:p.send(14);ping=now+.5
        t,d=p.receive();assert t!=4,(t,d)
        if t!=10:continue
        if first(p.inventory,4)>previous:break
        if now-last<.12:continue
        last=now;me=p.entities[p.id]
        npcs=[e for e in p.entities.values()if first(e,9)==1 and first(e,7)>0]
        if not npcs:continue
        npc=min(npcs,key=lambda e:(first(e,3)-first(me,3))**2+(first(e,5)-first(me,5))**2)
        dx,dz=first(npc,3)-first(me,3),first(npc,5)-first(me,5);distance=(dx*dx+dz*dz)**.5
        if distance<.9:p.move(0,0);p.action(first(npc,1))
        else:p.move(dx/max(1,distance),dz/max(1,distance))
    else:raise AssertionError('native party loot kill timeout')
    p.send(23);drop=next(fields(v)for v in p.until(24)[1].get(1,[])if first(fields(v),10)==1)
    p.send(25,integer(1,p.session)+integer(2,1)+integer(3,p.id)+integer(4,first(drop,1))+integer(5,first(drop,2))+blob(6,first(drop,3))+integer(7,first(drop,9)))
    while True:
        tag,result=p.until(26,4);assert tag==26,result
        if first(result,2)!=b'pending':break
    assert first(result,2)==b'claimed' and any(first(fields(v),2)==b'Companion' for v in result.get(7,[])),result
