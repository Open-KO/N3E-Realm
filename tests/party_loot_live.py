"""Original party item routing fixtures and live claims."""
import json,shutil,sys
from pathlib import Path
from isolation import once_per_run

@once_per_run
def prepare(full=False,alternate=False,ttl=600):
    from party_rewards_live import prepare as base
    source=base(full=full,alternate=alternate).parent/'source'
    root=Path('build/ko-completion/party-loot')/('full'if full else'alternate'if alternate else'base')/'source'
    root.mkdir(parents=True,exist_ok=True);shutil.copytree(source,root,dirs_exist_ok=True)
    m=json.loads((root/'package.json').read_text());m['engine_version']=26;m['protocol_version']=19
    m['progression']['model']='contribution_party_loot_v3';m['progression']['party_loot']={'radius':25 if alternate else 50}
    m['progression']['ttl']=ttl;m['gameplay']['health']=10000
    (root/'package.json').write_text(json.dumps(m));sys.path.insert(0,str(Path('tools/assetc').resolve()));import main
    out=root.parent/'package';main.cook(root,out);return out.resolve()

def audit(connect,restart,sql):
    import time
    from world_peer import Budget,first,fields,integer,blob
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
        p.send(25,integer(1,p.session)+integer(2,claim_seq[p])+integer(3,p.id)+integer(4,first(d,1))+integer(5,first(d,2))+blob(6,first(d,3))+integer(7,1))
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
    a=connect('explorer');peers.append(a);b=connect('companion');peers.append(b)
    assert command(a,1,'Companion')==b'invited'
    invitation=wait(b,43,lambda d:first(d,5)>0)
    assert command(b,2,token=first(invitation,5))==b'joined'
    wait(b,43,lambda d:len(d.get(4,[]))==2)
    kill(a);drop=drops(a)[0];assert drops(b)==[drop]
    c=connect('bystander');peers.append(c)
    assert not drops(c);denied=claim(c,drop);assert first(denied,2)==b'unknown' and not first(denied,5),denied
    c.send(27,integer(1,first(drop,1)));assert first(wait(c,26),2)==b'unknown'
    c.logout();peers.remove(c)
    walk(b,(first(drop,5),first(drop,7)))
    result=claim(b,drop);assert first(result,2)==b'claimed' and first(result,6)==b'Explorer',result
    wait(a,10,lambda _:first(a.inventory,2)==1)
    assert first(b.inventory,2)==0
    b.send(27,integer(1,first(drop,1)));assert wait(b,26)==result
    assert claim(a,drop)==result
    kill(a);second=drops(a)[0]
    result2=claim(a,second);assert first(result2,2)==b'claimed' and first(result2,6)==b'Companion',result2
    wait(b,10,lambda _:first(b.inventory,2)==1)
    assert first(a.inventory,2)==1
    assert sql('SELECT string_agg(cursor::text,\',\') FROM party_loot_cursors').strip()=='2'
    # Saved audience survives leaving. Current pickup membership determines routing.
    kill(a);third=drops(a)[0];left=command(b,4);assert left==b'disbanded',left
    walk(b,(first(third,5),first(third,7)))
    result3=claim(b,third);assert first(result3,2)==b'claimed' and first(result3,6)==b'Companion',result3
    wait(b,10,lambda _:first(b.inventory,2)==2)
    expected=sql('SELECT character_id,count FROM character_progress ORDER BY character_id')
    for p in peers:p.logout()
    peers.clear();restart()
    assert sql('SELECT character_id,count FROM character_progress ORDER BY character_id')==expected
    b=connect('companion');peers.append(b)
    b.send(27,integer(1,first(third,1)));assert wait(b,26)==result3
    assert not drops(b)
    a=connect('explorer');peers.append(a);c=connect('bystander');peers.append(c)
    for member,name in [(a,'Explorer'),(c,'Bystander')]:
        assert command(b,1,name)==b'invited'
        invite=wait(member,43,lambda d:first(d,5)>0)
        assert command(member,2,token=first(invite,5))==b'joined'
    wait(b,43,lambda d:len(d.get(4,[]))==3)
    kill(a);fourth=drops(a)[0];delivered=claim(a,fourth)
    assert first(delivered,2)==b'claimed' and first(delivered,6)==b'Companion',delivered
    notice=wait(c,26,lambda d:first(d,1)==first(fourth,1));assert notice==delivered
    wait(b,10,lambda _:first(b.inventory,2)==3)
    assert first(c.inventory,2)==0
    kill(a);fifth=drops(a)[0];walk(b,(first(fifth,5),first(fifth,7)))
    sql("CREATE FUNCTION delay_party_claim() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_sleep(0.5); RETURN NEW; END $$; CREATE TRIGGER delay_party_claim BEFORE INSERT ON party_loot_claims FOR EACH ROW EXECUTE FUNCTION delay_party_claim()")
    claim_seq[b]=claim_seq.get(b,0)+1
    b.send(25,integer(1,b.session)+integer(2,claim_seq[b])+integer(3,b.id)+integer(4,first(fifth,1))+integer(5,first(fifth,2))+blob(6,first(fifth,3))+integer(7,1))
    wait(b,26,lambda d:first(d,1)==first(fifth,1) and first(d,2)==b'pending')
    b.logout();peers.remove(b)
    sql('DROP TRIGGER delay_party_claim ON party_loot_claims; DROP FUNCTION delay_party_claim()')
    wait(a,10,lambda _:first(a.inventory,2)==2)
    for p in peers:p.logout()
    peers.clear()
    print('PASS TLS party audience, outsider list/claim/status isolation, requester-independent round robin, both live inventories, immutable cross-member retry, leave-before-pickup, restart recovery third-member notice and claimant logout during delayed delivery',flush=True)

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
    p.send(23);drop=fields(first(p.until(24)[1],1))
    p.send(25,integer(1,p.session)+integer(2,1)+integer(3,p.id)+integer(4,first(drop,1))+integer(5,first(drop,2))+blob(6,first(drop,3))+integer(7,1))
    while True:
        tag,result=p.until(26,4);assert tag==26,result
        if first(result,2)!=b'pending':break
    assert first(result,2)==b'claimed' and first(result,6)==b'Companion',result
