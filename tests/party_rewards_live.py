"""Original grouped-reward fixture and end-to-end settlement checks."""
import json,shutil,sys
from pathlib import Path
from isolation import once_per_run

@once_per_run
def prepare(full=False,alternate=False):
    from party_live import prepare as base
    source=base(full=full,alternate=alternate).parent/'source'
    root=Path('build/ko-completion/party-rewards')/('full'if full else'alternate'if alternate else'base')/'source'
    root.mkdir(parents=True,exist_ok=True);shutil.copytree(source,root,dirs_exist_ok=True)
    m=json.loads((root/'package.json').read_text());m['engine_version']=25;m['protocol_version']=18
    p=m['progression'];p['model']='contribution_party_v2'
    p['base_xp']=100;p['npc_level']=5
    # The audit checks reward distribution, not survival (PQ-112). The explorer
    # fights the first sentinel and then, solo, its respawn at full health, with
    # no health regeneration in between; at 100 health it died in about one run
    # in ten. Sentinel hits are at most 21 (contested_melee_v1 with the npc/player
    # stats above) every 20 ticks, from at most the two sentinels, and every kill()
    # gives up after its 60 s stall guard (PQ-123), so session 1 (25 s of join
    # waits, two kills, a 5 s wait) cannot spend 10000 (150 s x 2 x 21 = 6300). The descendant
    # party_loot, coin_loot, item_drops and reward_upgrades fixtures already use it.
    m['gameplay']['health']=10000
    p['thresholds']=[0,200,500,900,1400,2000,2700,3500,4400,5400]
    p['party_rewards']={'bonus_tenths':0 if alternate else 8,'level_minimum':2/3,'level_maximum':1.5,'level_gap':8,'level_xp':[200,300,400,500,600,700,800,900,1000,1100]}
    (root/'package.json').write_text(json.dumps(m));sys.path.insert(0,str(Path('tools/assetc').resolve()));import main
    out=root.parent/'package';main.cook(root,out);return out.resolve()

def audit(connect,restart,sql):
    import time
    from world_peer import DISCONNECTED,Budget,first,integer,blob
    peers=[];sequences={};pings={}
    def heartbeat():
        now=time.monotonic()
        for p in peers:
            if now-pings.get(p,0)>.5:p.send(14);pings[p]=now
    def wait(p,tag,predicate=lambda d:True):
        until=time.monotonic()+5
        while time.monotonic()<until:
            heartbeat();t,d=p.receive()
            assert t!=4,(t,d)
            if t==tag and predicate(d):return d
        raise AssertionError(('timeout',tag))
    def command(p,op=0,name='',token=0):
        sequences[p]=sequences.get(p,0)+1
        p.send(42,integer(1,sequences[p])+integer(2,op)+blob(3,name)+integer(4,token))
        return first(wait(p,44),2)
    def join():
        a,b=connect('explorer'),connect('companion');peers[:]=[a,b]
        assert command(a,1,'Companion')==b'invited'
        invite=wait(b,43,lambda d:first(d,5)>0)
        assert command(b,2,token=first(invite,5))==b'joined'
        wait(b,43,lambda d:len(d.get(4,[]))==2)
        return a,b
    def kill(a,b=None,crash=False):
        # Strikes hit 80 % and a kill takes three: bounded by 20 resolved strikes
        # (a spurious failure about 3e-11), not by time; the 60 s guard only
        # catches a stall and keeps the health bound above (PQ-123).
        previous=first(a.inventory,4);fight=Budget('no party kill',strikes=20,guard=60);last_input=0
        while fight.ok(a.entities,a.inventory):
            try:
                heartbeat();wait(a,10)
                if b:wait(b,10)
                if first(a.inventory,4)>previous:return
                if time.monotonic()-last_input<.12:continue
                last_input=time.monotonic()
                me=a.entities[a.id]
                # Fail at once, not at the deadline, if the fixture bound above breaks.
                assert first(me,7)>0,('explorer died during the kill',fight.last,a.entities)
                npcs=[e for e in a.entities.values()if first(e,9)==1 and first(e,7)>0]
                if not npcs:continue
                npc=min(npcs,key=lambda e:(first(e,3)-first(me,3))**2+(first(e,5)-first(me,5))**2)
                dx,dz=first(npc,3)-first(me,3),first(npc,5)-first(me,5);distance=(dx*dx+dz*dz)**.5
                if distance<.9:
                    a.move(0,0);heartbeat();fight.result(a.action(first(npc,1)))
                # Run (mode 1): each accepted move is one 50 ms step, and this loop
                # sends one about every 0.2 s, so walking used half the deadline.
                else:fight.step();a.move(dx/max(1,distance),dz/max(1,distance),mode=1)
            except DISCONNECTED:  # not a timeout (PQ-126)
                if crash:return
                raise
    def xp():
        return dict((name,int(value))for name,value in (line.split('|')for line in sql("SELECT c.name,p.xp FROM character_progress p JOIN characters c ON c.id=p.character_id ORDER BY c.name").strip().splitlines()))
    a,b=join();kill(a,b)
    assert xp()=={'Explorer':20,'Companion':20,'Bystander':0},xp()
    wait(b,10,lambda _:first(b.inventory,4)==20)
    proof=sql("SELECT c.name,r.credit,r.awarded_xp FROM encounter_recipients r JOIN characters c ON c.id=r.character_id ORDER BY c.name").strip().splitlines()
    assert proof==['Companion|0|20','Explorer|60|20'],proof
    # Consent and current membership matter: a departed member has no share of the next kill.
    b.logout();peers.remove(b);kill(a)
    assert xp()=={'Explorer':140,'Companion':20,'Bystander':0},xp()
    a.logout();peers.clear()
    for point in ['before_commit','after_commit']:
        before=xp();restart(settlement_fault=point);a,b=join();kill(a,b,crash=True)
        restart(expected_exit=86);peers.clear()
        expected={k:v+(20 if point=='after_commit' and k!='Bystander' else 0)for k,v in before.items()}
        assert xp()==expected,(point,xp(),expected)
        a,b=connect('explorer'),connect('companion');peers[:]=[a,b]
        for p,name in [(a,'Explorer'),(b,'Companion')]:
            assert first(p.inventory,4)==expected[name],(p.inventory,expected)
            assert command(p)==b'ok';s=wait(p,43);assert not first(s,2) and not first(s,5)
        for p in peers:p.logout()
        peers.clear()
    print('PASS TLS grouped kill, zero-damage member award, leave-before-kill solo fallback, before/after-COMMIT crash recovery and ephemeral group reset',flush=True)
