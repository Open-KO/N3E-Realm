"""Opt-in real TLS: accepted strike identity and rejection authority in Moradon."""
import json, os, secrets, subprocess, time
from pathlib import Path
from world_peer import Peer, fields, first, integer, blob
import moradon_stack
from moradon_route import to_worms, walker

state=moradon_stack.state()
package=moradon_stack.PACKAGE;manifest=json.loads((package/'recipe.json').read_text())['manifest']
assert manifest['protocol_version']>=29 and manifest['npc']['model']=='reference_melee_v2' and state['release']==(package/'release.sha256').read_text().strip()
env={**os.environ,'N3E_IMAGE':moradon_stack.IMAGE,'N3E_PACKAGE_PATH':str(package.resolve()),'N3E_PORT':str(state['port']),'N3E_REALM':state['realm']}
account='sequence'+secrets.token_hex(5);password=secrets.token_urlsafe(24)
subprocess.run(['docker','compose','-p',moradon_stack.PROJECT,'exec','-T','server','n3e-server','account-create',account],input=password+'\n',env=env,text=True,capture_output=True,check=True)
p=Peer(state['port'],account,password,content=state['release'],game=manifest['game_id'],protocol=manifest['protocol_version'])
try:
    p.select(p.create('Sequence'+secrets.token_hex(3)));p.pump(.3)
    def actor():return p.entities[p.id]
    # Reference worms live outside the town walls; the out-of-range probe needs one beyond reach.
    to_worms(walker(p,first,.5));p.pump(.5)
    def nearest():return min((e for e in p.entities.values() if first(e,9) and first(e,7) and (first(e,3)-first(actor(),3))**2+(first(e,5)-first(actor(),5))**2>2.25),key=lambda e:(first(e,3)-first(actor(),3))**2+(first(e,5)-first(actor(),5))**2)
    victim=nearest();target=first(victim,1);hp=first(victim,7)
    # Unknown fields cannot turn a request into a claimed hit, damage, or time.
    p.action_seq+=1
    p.send(15,integer(1,p.session)+integer(2,p.action_seq)+integer(3,target)+blob(4,p.action_id)+integer(5,999999)+integer(6,999999)+integer(7,1))
    result=p.until(16)[1];assert first(result,2)==b'out_of_range',result
    p.pump(.2);assert not first(actor(),30) and first(p.entities[target],7)==hp
    end=time.monotonic()+20
    while time.monotonic()<end:
        p.pump(.05);e=p.entities[target];dx=first(e,3)-first(actor(),3);dz=first(e,5)-first(actor(),5);distance=(dx*dx+dz*dz)**.5
        if distance<.7:p.move(0,0);p.pump(.15);break
        p.move(dx/max(1,distance),dz/max(1,distance),mode=1)
    else:raise AssertionError('approach timeout')
    result=p.action(target);seq=p.action_seq;assert result in ('hit','miss'),result
    end=time.monotonic()+1;seen=False
    while time.monotonic()<end:
        _,world=p.until(10)
        if first(actor(),30)!=seq:continue
        events=[fields(v) for v in world.get(14,[])]
        event=next((e for e in events if first(e,17)==seq and first(e,3)==p.id),None)
        assert event and first(event,4)==target and first(event,2)==first(actor(),10),(actor(),events)
        assert bool(first(event,9))==(result=='hit')
        seen=True;break
    assert seen,'accepted identity never published'
    strike=first(actor(),10)
    assert p.action(target,seq=seq)=='stale_action'
    assert p.action(target)=='cooldown'
    p.pump(.15);assert first(actor(),10)==strike and first(actor(),30)==seq
    print('PASS TLS forged outcome/time fields ignored, server range/cooldown/stale-sequence rejection, and accepted snapshot/event request identity')
finally:
    p.s.close()
