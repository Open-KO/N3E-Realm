"""Two ordinary TLS clients against a disposable native server and PG/Redis."""
import json
import os
import re
import shlex
from pathlib import Path
import subprocess
import sys
import time
import uuid
import shutil
import threading
from world_peer import Peer,first,integer,blob,fields,real
sys.path.insert(0,str(Path('tools/assetc').resolve()))
import main
from readiness import free_ports, wait_postgres
from isolation import DISPOSABLE_POSTGRES, container_logs
B=Path('build/p4');B.mkdir(parents=True,exist_ok=True)
source=B/'source';shutil.copytree('games/demo',source,dirs_exist_ok=True)
m=json.loads((source/'package.json').read_text());m['gameplay']['health']=10000;m['gameplay']['npc_health']=10
# PQ-177: the package styles an NPC info line; only the projected server.inspect
# capability shows it. The name display word equals the default (all shown, the
# toggle hides every class).
m['input']['names']={'shown':True,'hides':['self','players','npcs'],'npc_info':{'color':0x00FF00,'text':'ID({id}) : TYPE({state:0})'},
                    # PQ-178: the package styles a chat line the server marked as an operator's.
                    'operator_chat':{'color':0xCD9BFF}}
(source/'package.json').write_text(json.dumps(m));package=(B/'package').resolve();main.cook(source,package)
name='n3e-p4-'+uuid.uuid4().hex[:10];realm='test-'+name
password='test-only-'+uuid.uuid4().hex
containers=[];peers=[];server=None;logs=[];graphics=[]
env=dict(os.environ)

def run(*cmd,good=True,stdin=None):
    p=subprocess.run(cmd,env=env,input=stdin,capture_output=True,text=True,timeout=120)
    assert not good or p.returncode==0,(cmd,p.returncode,p.stdout,p.stderr)
    return p

def sql(q):return run('docker','exec',name,'psql','-U','n3e','-d','n3e','-Atc',q).stdout.strip()
def start():
    global server
    f=open(B/f'live-server-{len(logs)}.log','w');logs.append(f)
    server=subprocess.Popen(['target/debug/n3e-server'],env={k:v for k,v in env.items() if k!='N3E_TEST_PROGRESSION'},stdout=f,stderr=f)
    for _ in range(100):
        assert server.poll() is None,Path(f.name).read_text()
        try:
            import urllib.request
            if urllib.request.urlopen(f'http://127.0.0.1:{health}/ready',timeout=.2).status==200:return
        except Exception:time.sleep(.05)
    raise AssertionError('server not ready')
def connect(account,id=None):
    p=Peer(listen,account,password,content=(package/'release.sha256').read_text().strip(),protocol=6)
    peers.append(p)
    if id is None:id=p.create(account.upper())
    assert p.select(id)[0]==10
    p.pump(.15)
    return p,id

def req(p,op='publish',id=None,expected=0,patch=None,base=None,revision=0,session=None,extra=b''):
    id=id or uuid.uuid4().hex
    q=integer(1,p.session if session is None else session)+blob(2,id)+blob(3,op)+integer(4,expected)+blob(5,base or identity)+blob(7,'acceptance')+integer(8,revision)
    for k,v in (patch or {}).items():q+=blob(6,blob(1,k)+real(2,v))
    p.send(28,q+extra)
    return id

def result(p):
    while True:
        tag,r=p.until(29,4)
        if tag==4:return {2:[first(r,2)]}
        assert tag==29,r
        if first(r,2)!=b'pending':return r

def operation(p,**kw):req(p,**kw);return result(p)
def status(r):return first(r,2,b'').decode()
def snapshot(p):
    p.send(14);_,w=p.until(10);return fields(first(w,10,b''))
def values(s):return {first(fields(v),1).decode():first(fields(v),2) for v in s.get(4,[])}
def capabilities(p):
    """The capability set the server projects to this session (Registry, PQ-177)."""
    req(p,op='registry');_,reg=p.until(30);assert status(result(p))=='inspected'
    return sorted(c.decode() for c in reg.get(2,[]))
def trace(p,entity,id=None):
    """PQ-186: ask the server to mark NPC `entity` (AdminRequest.entity, field 10)."""
    return operation(p,op='trace',id=id,extra=integer(10,entity))
def watch(p,seconds):
    """World messages for `seconds`: (entity ids seen, {traced NPC: (state, its behavior)})."""
    seen=[];end=time.monotonic()+seconds;ping=0
    while time.monotonic()<end:
        if time.monotonic()>=ping:p.send(14);ping=time.monotonic()+.5
        _,w=p.until(10)
        ids={first(fields(e),1):first(fields(e),12,b'').decode() for e in w.get(4,[])}
        traced={first(fields(t),1):(first(fields(t),2,b'').decode(),ids.get(first(fields(t),1))) for t in w.get(17,[])}
        seen.append((set(ids),traced))
    return seen
def role(account,id,cap,grant=True):
    run('target/debug/n3e-server','role','grant' if grant else 'revoke',account,str(id),realm,cap)

def stop():
    global server
    for p in peers:
        try:p.s.close()
        except Exception:pass
    peers.clear()
    server.kill();server.wait();server=None;time.sleep(3.1)

try:
    # Pinned host ports (from the live slot's range): the Redis restart below must
    # keep its published port, which a Docker-assigned one does not guarantee.
    for container,image,container_port,extra in [(name,'postgres:17.4-bookworm@sha256:304ab813518754228f9f792f79d6da36359b82d8ecf418096c636725f8c930ad',5432,['-e','POSTGRES_USER=n3e','-e','POSTGRES_PASSWORD=test-only','-e','POSTGRES_DB=n3e',*DISPOSABLE_POSTGRES]),(name+'-redis','redis:7.4.2-bookworm@sha256:fbdbaea47b9ae4ecc2082ecdb4e1cea81e32176ffb1dcf643d422ad07427e5d9',6379,[])]:
        run('docker','run','--rm','-d','--name',container,*extra,'-p',f'127.0.0.1:{free_ports(1)[0]}:{container_port}',image);containers.append(container)
    pg=wait_postgres(name)
    redis=run('docker','port',name+'-redis','6379').stdout.strip();listen,health=free_ports(2)
    env.update(DATABASE_URL=f'host=127.0.0.1 port={pg} user=n3e password=test-only dbname=n3e',REDIS_ADDRESS=redis,N3E_REALM=realm,N3E_TEST_PROGRESSION='disposable',N3E_PACKAGE=str(package),N3E_LISTEN=f'127.0.0.1:{listen}',N3E_HEALTH=f'127.0.0.1:{health}')
    # wait_postgres proved the host path ready: any migration error is real.
    run('target/debug/n3e-server','migrate')
    run('target/debug/n3e-server','convert-progression')
    env['N3E_TEST_DATABASE_URL']=env['DATABASE_URL']
    dbtest=run('cargo','test','--locked','administration::tests::transaction_races_and_audit_rollback','--','--ignored','--exact','--nocapture');(B/'database.log').write_text(dbtest.stdout+dbtest.stderr)
    # 'c' is an ordinary bystander for the graphical round after the restart (PQ-184).
    for account in ['a','b','c']:run('target/debug/n3e-server','account-create',account,stdin=password+'\n')
    identity=(package/'release.sha256').read_text().strip();start();a,aid=connect('a');b,bid=connect('b')
    key='demo:lighting.intensity'
    assert status(operation(a,patch={key:.2},extra=integer(100,aid)+blob(101,'world.edit')+integer(102,1)))=='denied'
    role('a',aid,'world.edit');role('a',aid,'server.inspect');role('a',aid,'entity.spawn');role('b',bid,'world.edit')
    # PQ-177: the projection each session gets holds server.inspect only for the
    # holder; a revoked role leaves the next projection, which is the one refresh
    # point besides session start (no push on grant or revoke).
    assert capabilities(a)==['entity.spawn','server.inspect','world.edit'] and capabilities(b)==['world.edit']
    role('a',aid,'server.inspect',False);assert capabilities(a)==['entity.spawn','world.edit']
    role('a',aid,'server.inspect');assert 'server.inspect' in capabilities(a)
    # PQ-186: the operator NPC state trace. Only a server.inspect holder may mark
    # an NPC (the server checks the authenticated character's roles), and only a
    # session the server currently leases server.inspect receives the state of a
    # marked NPC it sees (World.traces), never one without the capability.
    npcs=sorted(i for i,e in a.entities.items() if first(e,9))
    assert npcs,'no NPC in view: the trace check proves nothing'
    target_npc=npcs[0]
    assert status(trace(b,target_npc))=='denied'
    assert status(trace(a,0))=='invalid_target' and status(trace(a,10**12))=='unknown_target'
    seen_b=watch(b,1.)
    assert any(target_npc in ids for ids,_ in seen_b) and not any(t for _,t in seen_b),'b saw a trace before any mark'
    assert status(trace(a,target_npc))=='traced' and status(trace(a,target_npc))=='traced'
    seen_a,seen_b=watch(a,1.5),watch(b,1.5)
    reported=[t[target_npc][0] for ids,t in seen_a if target_npc in t]
    assert reported,('holder got no trace',seen_a[-3:])
    assert all(set(t)<=set(npcs) and set(t)<=ids for ids,t in seen_a),'a trace named an unmarked or unseen entity'
    assert all(state==behavior for ids,t in seen_a for e,(state,behavior) in t.items()),'trace state differs from the NPC behavior'
    assert any(target_npc in ids for ids,_ in seen_b) and not any(t for _,t in seen_b),'a session without server.inspect got a trace'
    assert status(trace(b,target_npc))=='denied'
    # Revocation stops the reports within the lease (500 ms after the last read);
    # the mark stays, so a regrant brings them back.
    # The peer reads frames the socket buffered while it slept, so the first
    # 0.6 s of reading is drained before the check.
    role('a',aid,'server.inspect',False);time.sleep(.8);watch(a,.6)
    assert not any(t for _,t in watch(a,1.)),'reports after revocation'
    assert status(trace(a,target_npc))=='denied'
    role('a',aid,'server.inspect');time.sleep(.3)
    assert any(target_npc in t for _,t in watch(a,1.5)),'reports did not resume after the regrant'
    print('PASS NPC trace: holder marks and receives',sorted(set(reported)),'for NPC',target_npc,'; non-holder denied and never sent a trace; revocation stops reports within the lease')
    # PQ-189: the NPC snapshot record (KO's +pursue). Only a server.inspect holder
    # may ask; the server writes one line to its own log (stderr) off the tick and
    # answers with a status only. 'a' holds server.inspect again, 'b' never has.
    server_log=Path(logs[-1].name)
    def records():return [l for l in server_log.read_text().splitlines() if l.startswith('npc record ')]
    assert records()==[],'a record line before any request'
    assert status(operation(b,op='record',extra=integer(10,target_npc)))=='denied'
    assert status(operation(a,op='record',extra=integer(10,0)))=='invalid_target'
    for absent in (10**12,a.id):  # no such entity; a player, not an NPC
        assert status(operation(a,op='record',extra=integer(10,absent)))=='unknown_target',absent
    time.sleep(.5);assert records()==[],('a refused request wrote a line',records())
    # Two requests back to back: the second falls inside the session's interval.
    first_id=req(a,op='record',extra=integer(10,target_npc));second_id=req(a,op='record',extra=integer(10,target_npc))
    answers=[result(a),result(a)]
    assert [first(x,1).decode() for x in answers]==[first_id,second_id],answers
    assert [status(x) for x in answers]==['recorded','record_limit'],answers
    for x in answers:
        assert sorted(x)==[1,2],('the result carries more than its id and status',x)
    for _ in range(40):
        if records():break
        time.sleep(.05)
    time.sleep(.5);lines=records()
    assert len(lines)==1,lines
    got=dict(f.split('=',1) for f in shlex.split(lines[0][len('npc record '):]))
    assert set(got)=={'tick','entity','name','behavior','health','max_health','x','y','z'},got
    seen=a.entities.get(target_npc)
    assert seen is not None and int(got['entity'])==target_npc and got['name']==first(seen,2,b'').decode(),(got,seen)
    assert int(got['max_health'])==10 and 0<=int(got['health'])<=10 and re.fullmatch('[a-z_]+',got['behavior']),got
    assert all(abs(float(got[k])-first(seen,i,0.))<20 for k,i in (('x',3),('y',4),('z',5))),(got,seen)
    print('PASS NPC record: non-holder denied with no line; invalid, absent and player targets refused with no line; holder gets a status only and exactly one line',lines[0],'; a second request within the interval refused')
    # PQ-178: the server marks a chat line as an operator's (Chat.from_operator,
    # field 5) only while the sender's server.inspect lease is current, for every
    # receiver (the sender's own copy included); a request's field 5 is ignored.
    # 'a' holds server.inspect again, 'b' never has; both stand at the spawn point.
    def said(sender,text,forged=False):
        sender.send(11,blob(1,text)+(integer(5,1) if forged else b''))
        marks={}
        for p,label in ((a,'a'),(b,'b')):
            _,chat=p.until(11)
            assert first(chat,1)==text.encode() and first(chat,2)==sender.id and first(chat,4)==0,(label,chat)
            marks[label]=first(chat,5)
        time.sleep(1.1)  # one line a second per sender
        return marks
    assert said(b,'player line',forged=True)=={'a':0,'b':0},'a player line was marked'
    assert said(a,'operator line')=={'a':1,'b':1},'an operator line was not marked for every receiver'
    # PQ-184 (D-152): 'b' may not see the hidden 'a', so a private line from 'a'
    # is never marked for it (the mark would tell 'b' the role and whether 'a'
    # is in its interest area); a recipient that may see 'a' gets it marked.
    a.send(31,blob(1,'B')+blob(2,'operator whisper'));_,chat=b.until(11)
    assert first(chat,1)==b'operator whisper' and first(chat,4)==1 and first(chat,5)==0,('private line from a hidden operator',chat)
    time.sleep(1.1)
    role('b',bid,'server.inspect');time.sleep(.3)
    a.send(31,blob(1,'B')+blob(2,'operator whisper'));_,chat=b.until(11)
    assert first(chat,1)==b'operator whisper' and first(chat,4)==1 and first(chat,5)==1,('private line from an operator in view',chat)
    role('b',bid,'server.inspect',False)
    time.sleep(1.1)
    # The revoke returns once the simulation has applied it (D-150), so the very
    # next line is unmarked.
    role('a',aid,'server.inspect',False)
    assert said(a,'revoked line')=={'a':0,'b':0},'a revoked operator line was marked'
    role('a',aid,'server.inspect');time.sleep(.3)
    print('PASS operator chat mark: a player line (forged mark ignored) unmarked; an operator line marked for both receivers, the sender included, and in a private line to a recipient that may see the sender (unmarked to one that may not, PQ-184); the first line after the revoke unmarked')
    # PQ-184 (D-152): the server withholds a server.inspect holder from sessions
    # whose own server.inspect lease is not current: over the checked windows 'b'
    # receives no World that holds or names 'a' (entities, strike or cast
    # targets, presentation events), and a private line to 'A' is refused as to
    # an absent name. A holder sees the other holder; after a revocation 'a' is
    # in 'b''s first fresh World and every later one (the revoke returns once the
    # simulation has applied it, D-150).
    def worlds(p,seconds):
        seen=[];end=time.monotonic()+seconds;ping=0
        while time.monotonic()<end:
            if time.monotonic()>=ping:p.send(14);ping=time.monotonic()+.5
            _,w=p.until(10);es=[fields(e) for e in w.get(4,[])]
            named={first(e,1) for e in es}|{first(e,25) for e in es}|{first(e,29) for e in es}
            for v in w.get(14,[]):named|={first(fields(v),3),first(fields(v),4)}
            seen.append(({first(e,1) for e in es},named))
        return seen
    def hidden_from(observer,actor,seconds=1.5):
        worlds(observer,.6)  # Worlds the socket buffered before the change
        seen=worlds(observer,seconds);assert seen,'no World'
        return all(actor.id not in named for _,named in seen)
    def sees(observer,actor,seconds=1.5):
        return any(actor.id in ids for ids,_ in worlds(observer,seconds))
    assert sees(a,b),'the holder does not see the player: the check proves nothing'
    assert hidden_from(b,a),'a session without server.inspect received the operator'
    b.send(31,blob(1,'A')+blob(2,'to a hidden operator'));tag,error=b.until(4,11)
    assert tag==4 and first(error,2)==b'private message recipient unavailable',(tag,error)
    time.sleep(1.1)
    role('b',bid,'server.inspect');time.sleep(.3)
    assert sees(b,a) and sees(a,b),'one holder does not see the other'
    role('b',bid,'server.inspect',False)
    assert hidden_from(b,a,1.),'the operator reappeared to b after b lost server.inspect'
    role('a',aid,'server.inspect',False)
    # The first World after the buffered ones holds 'a', and every later one.
    seen=worlds(b,1.5);shown=next((i for i,(ids,_) in enumerate(seen) if a.id in ids),None)
    assert shown is not None and all(a.id in ids for ids,_ in seen[shown:]),('the operator was not visible after the revoke',shown,len(seen))
    b.send(31,blob(1,'A')+blob(2,'to a visible player'));_,chat=a.until(11)
    assert first(chat,1)==b'to a visible player',chat
    time.sleep(1.1)
    role('a',aid,'server.inspect');time.sleep(.3)
    assert hidden_from(b,a),'the operator was not hidden again after the regrant'
    print('PASS operator visibility: a server.inspect holder is withheld from a session without it (World, targets, events, private line refused); holders see each other; after the revoke the operator is shown; the regrant hides it again')
    # PQ-192 (D-153): the holder's show switch (KO's operator commands VIEW and
    # UNVIEW). 'b' (no server.inspect) is denied both; once 'b''s buffered
    # Worlds are drained, 'a' shown is in every World 'b' gets in a 1.5 s window,
    # and takes 'b''s private line; hidden again it is withheld; a revocation resets the switch, so the
    # regrant hides 'a' again. Read-only like trace: a status lookup is unknown.
    assert status(operation(b,op='show'))=='denied' and status(operation(b,op='hide'))=='denied'
    assert hidden_from(b,a,1.),'a non-holder\'s show changed the operator'
    assert status(operation(a,op='show',id='pq192-show'))=='shown'
    assert status(operation(a,op='status',id='pq192-show'))=='unknown'
    worlds(b,.6)  # Worlds the socket buffered before the switch
    seen=worlds(b,1.5)
    assert seen and all(a.id in ids for ids,_ in seen),('the shown operator was not in every World',[a.id in ids for ids,_ in seen])
    assert sees(a,b,1.),'the shown operator stopped seeing the player'
    b.send(31,blob(1,'A')+blob(2,'to a shown operator'));_,chat=a.until(11)
    assert first(chat,1)==b'to a shown operator',chat
    time.sleep(1.1)
    assert status(operation(a,op='hide'))=='hidden'
    assert hidden_from(b,a),'the operator was not withheld after hide'
    assert status(operation(a,op='show'))=='shown' and sees(b,a),'show after hide'
    role('a',aid,'server.inspect',False)
    assert status(operation(a,op='hide'))=='denied','a revoked character used the switch'
    role('a',aid,'server.inspect');time.sleep(.3)
    assert hidden_from(b,a),'the regrant did not hide the operator (the revocation kept the switch)'
    print('PASS operator show switch: a non-holder is denied; a shown holder is in every ordinary-session World of the window after the drain and takes its private line; hide withholds it again; a revocation resets the switch and the regrant hides it')
    assert status(operation(a,patch={key:.2},base='f'*64))=='incompatible_base'
    assert status(operation(a,patch={key:.2},session=a.session+1))=='stale_session'
    for k in ['demo:inventory.count','demo:xp.multiplier','demo:weather','demo:role','demo:treasury','demo:death.deadline','demo:decoration.banner.event']:
        assert status(operation(a,patch={k:1}))=='invalid_property',k
    assert status(operation(a,patch={'demo:collision.path':1}))=='restart_required'
    for k,v in [(key,float('nan')),(key,2),('demo:decoration.banner.visual',1),('demo:spawn.0.x',999)]:
        assert status(operation(a,patch={k:v}))=='invalid_property',(k,v)
    # Concurrent expected revision: exactly one wins; conflict contains full current values.
    req(a,id='race-a',patch={key:.2});req(b,id='race-b',patch={key:.3})
    ar,br=result(a),result(b);assert sorted([status(ar),status(br)])==['applied','conflict']
    winner=a if status(ar)=='applied' else b;winid='race-a' if winner is a else 'race-b';winval=.2 if winner is a else .3
    assert first(ar if status(ar)=='conflict' else br,5)
    # Cross-client full snapshots converge; stale delivery cannot patch over a new base.
    for p in [a,b]:
        for _ in range(15):
            s=snapshot(p)
            if first(s,2)==1:break
        assert abs(values(s)[key]-winval)<1e-5
    role('a' if winner is a else 'b',aid if winner is a else bid,'world.edit',False)
    assert status(operation(winner,id=winid,patch={key:winval}))=='applied'
    assert status(operation(winner,id=winid,patch={key:.7}))=='payload_conflict'
    assert status(operation(winner,expected=1,patch={key:.7}))=='denied'
    assert status(operation(winner,op='status',id=winid))=='applied'
    assert sql(f"SELECT count(*) FROM admin_audit WHERE realm='{realm}'")=='1'
    role('a',aid,'world.edit');role('b',bid,'world.edit')
    assert status(operation(a,expected=1,patch={'demo:decoration.banner.x':2,key:.65}))=='applied'
    assert status(operation(a,op='revert',expected=1,revision=0))=='conflict'
    assert status(operation(a,op='revert',expected=2,revision=0))=='applied'
    assert sql(f"SELECT count(*) FROM world_revisions WHERE realm='{realm}'")=='4'
    assert status(operation(a,op='spawn',id='temporary'))=='temporary_applied'
    assert status(operation(a,op='spawn',id='temporary'))=='temporary_applied'
    assert status(operation(b,op='spawn'))=='denied'
    assert status(operation(a,op='status',id='temporary'))=='temporary_applied'
    assert status(operation(a,op='spawn',id='temporary',extra=integer(9,1)))=='payload_conflict'
    for i in range(15):
        b.send(14);assert status(operation(a,op='spawn',id=f'bounded-{i}'))=='temporary_applied'
    assert status(operation(a,op='spawn',id='over-limit'))=='temporary_limit'
    # PQ-194 (D-157): the operator kill of a named NPC needs entity.kill, which
    # the server checks against the authenticated character; an authorized kill
    # is audited and the NPC dies through the ordinary death path (its
    # encounter settles). Two of the temporary NPCs above are the targets.
    def instance(request):
        return int(re.search(r'instance=(\d+)',first(operation(a,op='status',id=request),6,b'').decode()).group(1))
    def kill(p,entity,id=None):return operation(p,op='kill',id=id,extra=integer(10,entity))
    def audit(request):return sql(f"SELECT target||'|'||outcome FROM admin_audit WHERE realm='{realm}' AND request='{request}'")
    def settled(entity):return sql(f"SELECT count(*) FROM encounter_settlements WHERE realm='{realm}' AND encounter={entity}")
    victim,spare=instance('temporary'),instance('bounded-0')
    a.pump(.3);assert victim in a.entities and first(a.entities[victim],7)>0,'the kill target is not in view: the check proves nothing'
    assert status(kill(b,victim,'pq194-denied'))=='denied' and audit('pq194-denied')==''
    a.pump(.3);assert first(a.entities[victim],7)>0 and settled(victim)=='0','a refused kill changed the NPC'
    role('a',aid,'entity.kill')
    assert status(kill(a,0))=='invalid_target' and status(kill(a,10**12))=='unknown_target'
    assert status(kill(a,victim,'pq194-kill'))=='killed'
    assert status(kill(a,spare,'pq194-limit'))=='kill_limit','a second kill inside the interval'
    assert audit('pq194-kill')==f'kill:{victim}|kill_authorized',audit('pq194-kill')
    for _ in range(50):
        a.pump(.1)
        if settled(victim)=='1' and (victim not in a.entities or first(a.entities[victim],7)==0):break
    else:raise AssertionError(('the killed NPC did not die and settle',settled(victim),a.entities.get(victim)))
    # A stored authorization is never acted on again: a retry or status lookup
    # answers kill_replayed, so the kill_limit-refused request cannot kill later.
    assert status(kill(a,victim,'pq194-kill'))=='kill_replayed' and settled(victim)=='1'
    assert status(operation(a,op='status',id='pq194-kill'))=='kill_replayed' and settled(victim)=='1'
    time.sleep(1.1)  # past the interval: a fresh request could kill now
    assert status(kill(a,spare,'pq194-limit'))=='kill_replayed','a replayed refused kill was acted on'
    role('a',aid,'entity.kill',False)
    assert status(kill(a,spare,'pq194-revoked'))=='denied' and audit('pq194-revoked')==''
    assert status(kill(a,spare,'pq194-limit'))=='kill_replayed','a revoked operator replayed a stored kill'
    a.pump(.3);assert first(a.entities[spare],7)>0 and settled(spare)=='0','a replay or a revoked operator killed'
    print('PASS operator kill: a non-holder is denied and the NPC lives; the entity.kill holder kills the named NPC through the death path (settled, audited kill:'+str(victim)+'); a second kill inside the interval refused; a replayed or looked-up request answers kill_replayed and kills nothing, before and after the revocation; the revocation refuses the next')
    run('docker','restart',name+'-redis');a.send(14);b.send(14)
    import urllib.request
    for _ in range(60):
        a.pump(.05);b.pump(.05)
        try:
            if urllib.request.urlopen(f'http://127.0.0.1:{health}/ready',timeout=.2).status==200:break
        except Exception:pass
    else:raise AssertionError('readiness did not recover after Redis restart')
    assert first(snapshot(a),2)==3
    # Frozen definitions: publishing next-cycle values must not move current NPCs.
    old={i:(first(e,3),first(e,5)) for i,e in a.entities.items() if first(e,9)}
    assert status(operation(a,expected=3,patch={'demo:spawn.0.x':-7,'demo:npc.respawn_ticks':100}))=='applied'
    a.pump(.2)
    for i,pos in old.items():
        if i in a.entities:assert (first(a.entities[i],3),first(a.entities[i],5))==pos
    # Actual encounter: old cycle stays at its captured definition; replacement
    # receives the new position/timer and revision without rewriting the outcome.
    a.logout();peers.remove(a)
    sql(f"UPDATE characters SET x=-5,z=-5 WHERE id={aid}")
    a,_=connect('a',aid)
    target=min((i for i,e in a.entities.items() if first(e,9)),key=lambda i:abs(first(a.entities[i],3)+5)+abs(first(a.entities[i],5)+5))
    assert first(a.entities[target],18)==0
    killed=False
    for _ in range(80):
        b.send(14);a.action(target);a.pump(.1);b.pump(.1)
        if target not in a.entities or first(a.entities[target],7)==0:killed=True;break
    assert killed,'fixture NPC not defeated'
    settlement=sql(f"SELECT encode(payload,'hex') FROM encounter_settlements WHERE realm='{realm}' AND encounter={target}")
    assert settlement,'settlement not committed'
    replacement=None
    for _ in range(90):
        a.pump(.1);b.pump(.1)
        matches=[e for i,e in a.entities.items() if i!=target and first(e,9) and first(e,18)==4]
        if matches:replacement=matches[0];break
    assert replacement and abs(first(replacement,3)+7)<.5,'next-cycle spawn override missing'
    assert sql(f"SELECT encode(payload,'hex') FROM encounter_settlements WHERE realm='{realm}' AND encounter={target}")==settlement
    # Move reviewer back to the safe initial viewpoint after the combat fixture.
    a.logout();peers.remove(a);sql(f"UPDATE characters SET x=0,z=0 WHERE id={aid}")
    # Restart replay and lost acknowledgement, with real process exit at both boundaries.
    stop();start();a,_=connect('a',aid);b,_=connect('b',bid)
    assert first(snapshot(a),2)==4
    assert status(operation(a,op='status',id='temporary'))=='temporary_expired'
    for fault,expected,commits in [('before_commit',4,0),('after_commit',4,1)]:
        stop();env['N3E_ADMIN_FAULT']=fault;start();a,_=connect('a',aid)
        req(a,id=fault,expected=expected,patch={key:.4})
        server.wait(timeout=5);assert server.returncode==86
        assert sql(f"SELECT count(*) FROM admin_results WHERE realm='{realm}' AND request='{fault}'")==str(commits)
        stop();env.pop('N3E_ADMIN_FAULT');start();a,_=connect('a',aid);b,_=connect('b',bid)
        assert status(operation(a,id=fault,expected=expected,patch={key:.4}))==('applied' if commits else 'applied')
        if fault=='before_commit':
            # restore expected 4 for the next fault via actual current revision below
            expected=5
        if fault=='before_commit':break
    stop();env['N3E_ADMIN_FAULT']='after_commit';start();a,_=connect('a',aid)
    req(a,id='after_commit',expected=5,patch={key:.6});server.wait(timeout=5);assert server.returncode==86
    stop();env.pop('N3E_ADMIN_FAULT');start();a,_=connect('a',aid);b,_=connect('b',bid)
    assert first(snapshot(a),2)==6
    assert status(operation(a,id='after_commit',expected=5,patch={key:.6}))=='applied'
    assert sql(f"SELECT count(*) FROM admin_results WHERE realm='{realm}' AND request='after_commit'")=='1'
    assert sql(f"SELECT count(*) FROM admin_audit WHERE realm='{realm}' AND request='after_commit'")=='1'
    assert status(operation(b,op='status',id='after_commit'))=='unknown'
    # Export the complete applied snapshot and rebuild; absolute values are baked once.
    s=snapshot(a);raw=blob(1,first(s,1))+integer(2,first(s,2))+b''.join(blob(4,v) for v in s[4]);(B/'export.n3draft').write_bytes(raw)
    import drafts
    destination=B/('export-'+uuid.uuid4().hex[:8]);newhash=drafts.export(source,B/'export.n3draft',destination)
    assert newhash!=identity
    assert abs(json.loads((destination/'package.json').read_text())['editing']['lighting']-.6)<1e-5
    assert (destination/'cooked/progression.bin').read_bytes()==(package/'progression.bin').read_bytes()
    try:drafts.export(destination,B/'export.n3draft',B/'invalid-export')
    except ValueError:pass
    else:raise AssertionError('incompatible export accepted')
    import shutil
    cosmetic=B/('cosmetic-'+uuid.uuid4().hex[:8]);shutil.copytree(source,cosmetic)
    m=json.loads((cosmetic/'package.json').read_text());m['editing']['lighting']=.1;(cosmetic/'package.json').write_text(json.dumps(m))
    rebased=B/('rebased-'+uuid.uuid4().hex[:8]+'.n3draft');drafts.rebase(source,cosmetic,B/'export.n3draft',rebased)
    drafts.export(cosmetic,rebased,B/('rebased-export-'+uuid.uuid4().hex[:8]))
    try:drafts.rebase(source,destination,B/'export.n3draft',B/'invalid-rebase.n3draft')
    except ValueError:pass
    else:raise AssertionError('authoritative rebase accepted')
    if os.getenv('N3E_GRAPHICAL')=='1':
        # PQ-186: mark the NPCs near the spawn point; the marks outlive this
        # session (as KO's flag outlives the +actpursue sender) and end with the
        # server, so the editing round's holder sees traced lines and the
        # restarted round's sees none.
        marked=sorted(i for i,e in a.entities.items() if first(e,9))[:8]
        assert marked and all(status(trace(a,i))=='traced' for i in marked),marked
        for p in peers:p.logout()
        peers.clear()
        # PQ-177: 'a' holds server.inspect, 'b' does not. Each client counts the
        # NPC name labels it draws and the info lines drawn with them
        # (N3E_TEST_NPC_INFO); the line follows the projection only, so 'b'
        # draws none in the player build or the tools build.
        # PQ-178: one client says a local line (N3E_TEST_CHAT) once the other
        # is in view; each prints the last line it received, its server mark
        # and the colour its HUD drew it in (CHAT_LINE).
        def graphical_round(prefix,clients,speaker,line,marked):
            processes=[]
            for account,tools,editor in clients:
                out=B/f'{prefix}-{account}.log';f=open(out,'w');logs.append(f)
                binary='build/client-tools/n3e-test-client' if tools else 'build/client/n3e-test-client'
                ge={**env,'N3E_TEST_ACCOUNT':account,'N3E_TEST_PASSWORD':password,'N3E_EDIT_TEST' if editor else 'N3E_EDIT_OBSERVE':'1','N3E_TEST_NPC_INFO':'1'}
                ge['N3E_TEST_CHAT']=line if account==speaker else ''  # empty: listen and report only
                proc=subprocess.Popen([binary,str(package),'--connect',f'localhost:{listen}','--ca','deploy/local/ca.pem','--npc-observe','8','--capture',str(B/f'{prefix}-{account}.ppm')],env=ge,stdout=f,stderr=f);processes.append((account,tools,proc,out))
            for account,tools,proc,out in processes:
                proc.wait(timeout=25);text=out.read_text();assert proc.returncode==0,text;assert 'EDIT visible revision=' in text
                info=[l for l in text.splitlines() if l.startswith('NPC_INFO ')];assert len(info)==1,text
                head,rest=info[0].split(' text=',1);text_field,traced_text=rest.split(' traced_text=',1)
                fields=dict(x.split('=',1) for x in head.split(' ')[1:])
                assert int(fields['names'])>0,f'{prefix}-{account}: no NPC name drawn, the check proves nothing: {info[0]}'
                if account=='a':
                    assert fields['inspect']=='1' and int(fields['lines'])>0 and text_field.startswith('ID(') and text_field.endswith(')'),info[0]
                    # PQ-186: marked NPCs show the reported state, the others 0;
                    # after the restart nothing is marked.
                    if prefix=='editing':assert int(fields['traced'])>0 and traced_text.startswith('ID(') and traced_text.endswith(')') and not traced_text.endswith('TYPE(0)'),info[0]
                    else:assert fields['traced']=='0' and text_field.endswith(') : TYPE(0)'),info[0]
                else:assert fields['inspect']=='0' and fields['lines']=='0' and fields['traced']=='0' and text_field=='' and traced_text=='',info[0]
                print(f'NPC_INFO {prefix} {account} tools={int(tools)} {info[0][9:]}')
                said=[l for l in text.splitlines() if l.startswith('CHAT_LINE ')];assert len(said)==1,text
                head,received=said[0].split(' text=',1);fields=dict(x.split('=',1) for x in head.split(' ')[1:])
                assert received==f'{speaker.upper()}: {line}' and fields['sent']==str(int(account==speaker)),said[0]
                assert fields['operator']==str(int(marked)) and fields['drawn'].endswith('cd9bff')==marked and fields['drawn']!='none',said[0]
                print(f'CHAT_LINE {prefix} {account} tools={int(tools)} {said[0][10:]}')
        graphical_round('editing',[('a',True,True),('b',False,False)],'a','operator line',True)
        # PQ-184: 'a' still holds server.inspect, so 'b' does not see it; the
        # speaker 'b' waits for another player in view, so the ordinary 'c'
        # (a TLS peer, kept read) stands at the spawn point during the round.
        stop();start();c,_=connect('c');c_stop=threading.Event()
        def keep_c():
            while not c_stop.is_set():
                try:c.receive()
                except TimeoutError:pass
        c_thread=threading.Thread(target=keep_c,daemon=True);c_thread.start()
        try:graphical_round('restarted',[('a',False,False),('b',True,False)],'b','player line',False)
        finally:c_stop.set();c_thread.join(timeout=5)
        print('PASS simultaneous tools publisher/normal observer and normal/tools observers after restart; NPC info line only with the projected server.inspect; traced NPC state only to the holder; operator chat colour only on a server-marked line')
    assert sql(f"SELECT encode(payload,'hex') FROM encounter_settlements WHERE realm='{realm}' AND encounter={target}")==settlement
    # Rebuild/redeploy into an explicitly new realm: overrides are already baked.
    stop();package=(destination/'cooked').resolve();env['N3E_PACKAGE']=str(package)
    # Existing realm must fail before readiness on a different release identity.
    mismatch=run('target/debug/n3e-server',good=False)
    assert mismatch.returncode!=0 and 'incompatible_base' in mismatch.stderr,mismatch.stderr
    realm=realm+'-export';env['N3E_REALM']=realm;env['N3E_TEST_PROGRESSION']='disposable'
    run('target/debug/n3e-server','convert-progression');identity=newhash
    start();a,newaid=connect('a')
    exported=snapshot(a);assert first(exported,2)==0 and abs(values(exported)[key]-.6)<1e-5
    print('PASS export/redeploy starts at revision zero with baked values; incompatible existing realm fails before readiness')
    print('PASS P4 direct TLS authority, role revocation/retry, race/conflict, validation, broadcast, temporary dedup, restart, commit crashes, revert, export')
finally:
    for p in peers:
        try:p.s.close()
        except Exception:pass
    if server is not None and server.poll() is None:server.kill();server.wait()
    for f in logs:f.close()
    # PQ-128: each container's log, before it is removed.
    for c in containers:container_logs({name:'postgres',name+'-redis':'redis'}[c],['docker','logs','--timestamps',c])
    for c in reversed(containers):run('docker','rm','-f',c,good=False)
