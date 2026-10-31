"""TLS preservation of earned XP, an old pending claim and new grouped rewards."""
import time
from pathlib import Path
from world_peer import Budget,first,fields,integer,blob,real

def audit(connect,restart,sql):
    target=Path('build/ko-completion/reward-upgrades/target/package').resolve()
    peers=[];pings={}
    def heartbeat():
        now=time.monotonic()
        for p in peers:
            if now-pings.get(p,0)>.5:p.send(14);pings[p]=now
    def wait(p,tag,predicate=lambda _:True):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            heartbeat();t,d=p.receive();assert t!=4,(t,d)
            if t==tag and predicate(d):return d
        raise AssertionError(('timeout',tag))
    def kill(p,other=None):
        # Strikes hit 80 % (contested_melee_v1 accuracy 50 against evasion 100) and a
        # kill takes three: bounded by 20 resolved strikes (a spurious failure about
        # 3e-11), not by time; the 90 s guard only catches a stall (PQ-123).
        previous=first(p.inventory,4);fight=Budget('kill',strikes=20,guard=90);last_input=0
        while fight.ok(p.inventory,p.entities):
            wait(p,10)
            if other:wait(other,10)
            if first(p.inventory,4)>previous:return
            if time.monotonic()-last_input<.12:continue
            last_input=time.monotonic();me=p.entities[p.id]
            assert first(me,7)>0,('player died during the kill',fight.last,p.entities)
            npcs=[e for e in p.entities.values()if first(e,9)==1 and first(e,7)>0]
            if not npcs:continue
            npc=min(npcs,key=lambda e:(first(e,3)-first(me,3))**2+(first(e,5)-first(me,5))**2)
            dx,dz=first(npc,3)-first(me,3),first(npc,5)-first(me,5);d=(dx*dx+dz*dz)**.5
            if d<.9:p.move(0,0);fight.result(p.action(first(npc,1)))
            else:fight.step();p.move(dx/max(1,d),dz/max(1,d))
    def drops(p):p.send(23);return [fields(v)for v in wait(p,24).get(1,[])]
    a=connect('explorer');peers[:]=[a]
    w=wait(a,10);saved_world=fields(first(w,10))
    if int(sql("SELECT count(*) FROM character_roles r JOIN characters c ON c.id=r.character_id WHERE c.name='Explorer' AND r.capability='world.edit'").strip()):
        a.send(28,integer(1,a.session)+blob(2,'upgrade-registry')+blob(3,'registry'))
        registry=wait(a,30);state=fields(first(wait(a,29),5))
        light=next(fields(v)for v in registry[1]if first(fields(v),10)==0)
        a.send(28,integer(1,a.session)+blob(2,'upgrade-light')+blob(3,'publish')+integer(4,first(state,2))+blob(5,first(state,1))+blob(6,blob(1,first(light,1))+real(2,.23))+blob(7,'preserve through reward upgrade'))
        result=wait(a,29,lambda d:first(d,2)!=b'pending');assert first(result,2)==b'applied',result
        saved_world=fields(first(result,5))
    kill(a)
    assert first(a.inventory,4)==120,a.inventory
    old=drops(a);assert len(old)==1,old;drop=old[0]
    before=sql("SELECT c.name,p.xp,r.curve_xp,r.baseline_xp,r.baseline_level,r.baseline_remainder FROM character_progress p JOIN character_reward_progress r USING(character_id) JOIN characters c ON c.id=p.character_id ORDER BY c.name")
    immutable=sql("SELECT md5(string_agg(row_to_json(s)::text,'' ORDER BY encounter)) FROM encounter_settlements s")
    restart(upgrade_package=target,upgrade_active=True)
    a.logout();peers.clear();restart(upgrade_package=target)
    assert sql("SELECT c.name,p.xp,r.curve_xp,r.baseline_xp,r.baseline_level,r.baseline_remainder FROM character_progress p JOIN character_reward_progress r USING(character_id) JOIN characters c ON c.id=p.character_id ORDER BY c.name")==before
    assert sql("SELECT md5(string_agg(row_to_json(s)::text,'' ORDER BY encounter)) FROM encounter_settlements s")==immutable
    a=connect('explorer');peers[:]=[a];assert first(a.inventory,4)==120;assert drops(a)==old
    state=fields(first(wait(a,10),10));assert state.get(4)==saved_world.get(4),(state,saved_world)
    assert first(state,2)==first(saved_world,2)+1 and first(state,1).decode()==(target/'release.sha256').read_text().strip()
    # Stand outside the destination's radius1 but inside the earned radius3.
    goal=(first(drop,5)+2,first(drop,7));deadline=time.monotonic()+12;last_input=0
    while time.monotonic()<deadline:
        wait(a,10);me=a.entities[a.id]
        dx,dz=goal[0]-first(me,3),goal[1]-first(me,5);d=(dx*dx+dz*dz)**.5
        if time.monotonic()-last_input<.12:continue
        last_input=time.monotonic()
        if d<.15:a.move(0,0);break
        a.move(dx/max(1,d),dz/max(1,d))
    else:raise AssertionError('old drop approach timeout')
    a.pump(.2);me=a.entities[a.id]
    distance=sum((first(me,i+3)-first(drop,i+5))**2 for i in range(3))**.5
    assert 1<distance<3,(distance,me,drop)
    q=integer(1,a.session)+integer(2,1)+integer(3,a.id)+integer(4,first(drop,1))+integer(5,first(drop,2))+blob(6,first(drop,3))+integer(7,1)
    a.send(25,q);result=wait(a,26,lambda d:first(d,2)!=b'pending');assert first(result,2)==b'claimed',result
    a.send(27,integer(1,first(drop,1)));assert wait(a,26)==result
    wait(a,10,lambda _:first(a.inventory,2)==1);assert first(a.inventory,4)==120
    b=connect('companion');peers.append(b)
    a.send(42,integer(1,1)+integer(2,1)+blob(3,'Companion'));invited=wait(a,44);assert first(invited,2)==b'invited',invited
    invite=wait(b,43,lambda d:first(d,5)>0)
    b.send(42,integer(1,1)+integer(2,2)+integer(4,first(invite,5)));assert first(wait(b,44),2)==b'joined'
    wait(b,43,lambda d:len(d.get(4,[]))==2);kill(a,b)
    wait(b,10,lambda _:first(b.inventory,4)==20)
    assert first(a.inventory,4)==140,a.inventory
    for p in peers:p.logout()
    peers.clear()
    print('PASS TLS offline upgrade, live-owner rejection, preserved XP/baselines/history, old pending claim at original radius, exact claim retry and new grouped XP',flush=True)
