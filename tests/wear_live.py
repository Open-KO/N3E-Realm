"""Original ordinary-wear fixture; authoritative commit, break and repair checks."""
import json,shutil,sys,time
from pathlib import Path
from world_peer import DISCONNECTED,Budget,fields,first,integer,blob
from isolation import once_per_run

@once_per_run
def prepare():
    from stats_live import prepare as stats_prepare
    stats_prepare();root=Path('build/ko-completion/wear/source');root.mkdir(parents=True,exist_ok=True)
    shutil.copytree('build/ko-completion/stats/source',root,dirs_exist_ok=True)
    m=json.loads((root/'package.json').read_text());m['engine_version']=20;m['protocol_version']=13
    m['gameplay']['npc_health']=300;m['gameplay']['spawns']=[[-5,-5]]
    m['damage']['npc'].update(attack=18,defense=0,accuracy=100,evasion=1)
    for i in m['inventory']['items']:
        if i['id'].endswith(('blade','shield')):i['durability']=3
    for item in m['stats']['items']:
        if item['id'].endswith('ring'):item['health']=200
    m['wear']={'scale':.1,'items':[dict(id=i['id'],attack_slots=i['slots']if i['id'].endswith(('blade','twohand'))else [],defense_slots=i['slots']if i['id'].endswith('shield')else [])for i in m['equipment']['items']]}
    (root/'package.json').write_text(json.dumps(m));sys.path.insert(0,str(Path('tools/assetc').resolve()));import main
    package=Path('build/ko-completion/wear/package');main.cook(root,package);return package.resolve()

def audit(connect,restart,sql):
    p=connect('explorer');state=None
    def recv():
        nonlocal state
        tag,data=p.receive()
        if tag==33:
            candidate=fields(first(data,3))
            if state is None or first(candidate,1)>=first(state,1):state=candidate
        return tag,data
    def req(q=b'',name=b'',status=b'ok'):
        p.send(32,q);end=time.monotonic()+4
        while time.monotonic()<end:
            tag,data=recv()
            if tag==33 and first(data,1,b'')==name and first(data,2)==status:return data
            assert tag!=4,(tag,data)
        raise AssertionError(('missing bag reply',name,status))
    req();serial=first(fields(state[5][0]),1)
    for name,source,destination in [('blade',0,0),('shield',2,1),('ring',4,2)]:
        q=integer(1,5)+blob(2,name)+integer(3,first(state,1))+integer(4,source)+integer(5,destination)+integer(6,first(fields(state[5][source]),1));req(q,name.encode(),b'committed')
    p.logout();p=connect('explorer');req()
    # The network cannot manufacture the server's durability event.
    p.send(32,integer(1,9)+blob(2,'forged-wear')+integer(3,first(state,1))+integer(6,serial));tag,data=p.until(4);assert first(data,1)==4
    sql("CREATE FUNCTION delay_wear() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_sleep(0.3); RETURN NEW; END $$; CREATE TRIGGER delay_wear BEFORE INSERT ON durability_operations FOR EACH ROW EXECUTE FUNCTION delay_wear()")
    # Strikes hit 92 % here (derived accuracy 1.76 against sentinel evasion 1), so
    # the three hits are bounded by 12 resolved strikes (a spurious failure under
    # 1e-9), not by time (PQ-123; 18 s left a load-dependent number of strikes).
    fight=Budget('three outgoing wear hits',strikes=12);hits=0;events=0;waiting=None;last_sent=0;frames=0
    while hits<3 and fight.ok(hits,state):
        tag,data=recv()
        if tag==33 and first(data,2)==b'worn':events+=1
        if tag==16:
            fight.result(first(data,2),hits,state)
            if first(data,2)==b'hit':
                assert events>0,'hit acknowledged before durable wear result';hits+=1
                assert frames>=2,('tick did not advance during delayed wear',frames)
                assert int(sql("SELECT count(*) FROM durability_operations WHERE committed AND get_byte(payload,36)=1"))==hits
                assert first(fields(state[6][0]),1)==serial
                assert first(fields(state[6][0]),4)==3-hits,(hits,state)
            waiting=None
        if tag==10:
            if waiting is not None:frames+=1
            me=p.entities[p.id];assert first(me,7)>0,('unexpected fixture death',hits,state)
            npc=next(e for e in p.entities.values()if first(e,9)==1)
            dx=first(npc,3)-first(me,3);dz=first(npc,5)-first(me,5);d=(dx*dx+dz*dz)**.5
            if d>0.9:fight.step(hits,state);p.move(dx/max(1,d),dz/max(1,d))
            else:
                p.move(0,0)
                if waiting is None and time.monotonic()-last_sent>1.1:
                    p.action_seq+=1;waiting=p.action_seq;last_sent=time.monotonic();frames=0
                    p.send(15,integer(1,p.session)+integer(2,waiting)+integer(3,first(npc,1))+blob(4,p.action_id))
    assert hits==3,(hits,state)
    assert first(fields(state[6][1]),4)<3,'incoming damage did not wear shield'
    sql('DROP TRIGGER delay_wear ON durability_operations; DROP FUNCTION delay_wear()')
    # Logging out during a potential defensive wear operation drains its commit.
    p.logout();restart();p=connect('explorer');req();assert first(fields(state[6][0]),4)==0
    before=state;repair=integer(1,8)+blob(2,'wear-repair')+integer(3,first(state,1))+integer(6,serial)+blob(8,'demo:item/blade')
    result=req(repair,b'wear-repair',b'committed');assert first(fields(state[6][0]),4)==3 and first(state,4)<first(before,4)
    p.logout();restart();p=connect('explorer');req();saved=state
    again=req(repair,b'wear-repair',b'committed');assert again==result;req();assert state==saved
    assert int(sql("SELECT count(*) FROM durability_operations WHERE committed"))>=hits
    # Remove defensive wear so only the intended outgoing event triggers each crash.
    if fields(state[6][1]):
        q=integer(1,6)+blob(2,'crash-unshield')+integer(3,first(state,1))+integer(4,1)+integer(5,2)+integer(6,first(fields(state[6][1]),1));req(q,b'crash-unshield',b'committed')
    for phase in ['before_commit','after_commit']:
        before=state;count=int(sql("SELECT count(*) FROM durability_operations"));p.logout()
        sql("UPDATE characters SET x=0,z=0 WHERE name='Explorer'")
        restart(wear_fault=phase);p=connect('explorer');req();before=state
        # The crash needs one 92 % hit: 10 resolved strikes, not 10 s (PQ-123).
        fight=Budget(('wear crash did not happen',phase),strikes=10,guard=60);closed=False;last=0
        try:
            while fight.ok():
                tag,data=recv()
                if tag==16:assert first(data,2)!=b'hit',('hit published before crash',phase,data);fight.result(first(data,2),data)
                if tag==10:
                    me=p.entities[p.id];npc=next(e for e in p.entities.values()if first(e,9)==1);assert first(npc,7)==300
                    dx=first(npc,3)-first(me,3);dz=first(npc,5)-first(me,5);distance=(dx*dx+dz*dz)**.5
                    if distance>.9:fight.step();p.move(dx/max(1,distance),dz/max(1,distance))
                    else:
                        p.move(0,0)
                        if time.monotonic()-last>1.1:
                            last=time.monotonic();p.action_seq+=1;p.send(15,integer(1,p.session)+integer(2,p.action_seq)+integer(3,first(npc,1))+blob(4,p.action_id))
        except DISCONNECTED:closed=True  # not a timeout (PQ-126)
        assert closed,('wear crash did not happen',phase)
        restart(expected_exit=94);p=connect('explorer');req()
        delta=1 if phase=='after_commit'else 0
        assert first(state,1)==first(before,1)+delta
        assert first(fields(state[6][0]),4)==first(fields(before[6][0]),4)-delta
        assert first(state,4)==first(before,4)
        assert int(sql("SELECT count(*) FROM durability_operations"))==count+delta
        assert first(p.inventory,4)==0,'unpublished hit granted XP'
    p.logout();p=connect('companion');state=None;req()
    for name,source,destination in [('view-blade',0,0),('view-shield',2,1),('view-ring',4,2)]:
        q=integer(1,5)+blob(2,name)+integer(3,first(state,1))+integer(4,source)+integer(5,destination)+integer(6,first(fields(state[5][source]),1));req(q,name.encode(),b'committed')
    p.logout();print('PASS server-only wear, durable hit ordering under delayed commits, weapon break, defensive shield wear, repair, logout drain, before/after-COMMIT process crashes and hard restart',flush=True)
