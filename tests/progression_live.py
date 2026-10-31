"""Two ordinary TLS clients against a disposable native server and PG/Redis."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid
from world_peer import Peer,first,integer
sys.path.insert(0,str(Path('tools/assetc').resolve()))
import progression_fixture,main
from readiness import free_ports, wait_postgres
from isolation import DISPOSABLE_POSTGRES, container_logs
B=Path('build/ko-09');B.mkdir(parents=True,exist_ok=True)
progression_fixture.cook()
root=Path('build/progression-source');m=json.loads((root/'package.json').read_text())
m['gameplay'].update(health=10000,resource=100,cost=1,regen_ticks=1,npc_damage=1,aggro_range=0.05,respawn_ticks=20,starting_items=2)
m['progression']['starting']=2
(root/'package.json').write_text(json.dumps(m))
package=(B/'live-package').resolve();main.cook(root,package)
name='n3e-ko09-live-'+uuid.uuid4().hex[:10];realm='test-'+name
password='test-only-'+uuid.uuid4().hex
containers=[];peers=[];server=None;logs=[]
env=dict(os.environ)

def run(*cmd,good=True,stdin=None):
    p=subprocess.run(cmd,env=env,input=stdin,capture_output=True,text=True,timeout=120)
    assert not good or p.returncode==0,(cmd,p.returncode,p.stdout,p.stderr)
    return p

def sql(q):return run('docker','exec',name,'psql','-U','n3e','-d','n3e','-Atc',q).stdout.strip()
def port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
def start():
    global server
    f=open(B/f'live-server-{len(logs)}.log','w');logs.append(f)
    server=subprocess.Popen(['target/debug/n3e-server'],env=env,stdout=f,stderr=f)
    for _ in range(100):
        assert server.poll() is None,Path(f.name).read_text()
        try:
            import urllib.request
            if urllib.request.urlopen(f'http://127.0.0.1:{health}/ready',timeout=.2).status==200:return
        except Exception:time.sleep(.05)
    raise AssertionError('server not ready')
def connect(account,id=None):
    p=Peer(listen,account,password,content=(package/'release.sha256').read_text().strip(),protocol=4)
    peers.append(p)
    if id is None:id=p.create(account.upper())
    assert p.select(id)[0]==10
    p.pump(.15)
    return p,id

def npc(p,previous=0):
    for _ in range(40):
        p.pump(.1)
        v=[id for id,e in p.entities.items() if first(e,9) and first(e,7)>0 and id!=previous]
        if v:return v[0]
    raise AssertionError('NPC respawn')
def status(p,encounter):
    p.send(21,integer(1,encounter));tag,data=p.until(22,4);assert tag==22,data;return data

def committed(encounter):
    for _ in range(100):
        row=sql(f"SELECT outcome FROM encounter_settlements WHERE realm='{realm}' AND encounter={encounter}")
        if row:return row
        time.sleep(.02)
    raise AssertionError('no committed settlement')
try:
    for container,image,container_port,extra in [(name,'postgres:17.4-bookworm@sha256:304ab813518754228f9f792f79d6da36359b82d8ecf418096c636725f8c930ad',5432,['-e','POSTGRES_USER=n3e','-e','POSTGRES_PASSWORD=test-only','-e','POSTGRES_DB=n3e',*DISPOSABLE_POSTGRES]),(name+'-redis','redis:7.4.2-bookworm@sha256:fbdbaea47b9ae4ecc2082ecdb4e1cea81e32176ffb1dcf643d422ad07427e5d9',6379,[])]:
        run('docker','run','--rm','-d','--name',container,*extra,'-p',f'127.0.0.1::{container_port}',image);containers.append(container)
    pg=wait_postgres(name)
    redis=run('docker','port',name+'-redis','6379').stdout.strip()
    listen,health=free_ports(2)
    env.update(DATABASE_URL=f'host=127.0.0.1 port={pg} user=n3e password=test-only dbname=n3e',REDIS_ADDRESS=redis,N3E_REALM=realm,N3E_TEST_PROGRESSION='disposable',N3E_PACKAGE=str(package),N3E_LISTEN=f'127.0.0.1:{listen}',N3E_HEALTH=f'127.0.0.1:{health}')
    # wait_postgres proved the host path ready: any migration error is real.
    run('target/debug/n3e-server','migrate')
    run('target/debug/n3e-server','convert-progression')
    for account in ['a','b','outsider']:run('target/debug/n3e-server','account-create',account,stdin=password+'\n')
    start();a,aid=connect('a');b,bid=connect('b');other,oid=connect('outsider')
    n=npc(a);assert a.action(n)=='hit';assert b.action(n)=='hit';assert committed(n)=='entitled'
    assert sql(f"SELECT character_id||':'||credit||':'||awarded_xp FROM encounter_recipients WHERE encounter={n} ORDER BY character_id")==f'{aid}:60:6\n{bid}:40:4'
    assert first(status(a,n),3)==6 and first(status(b,n),3)==4
    assert first(status(other,n),2)==b'unknown'
    other.logout();peers.remove(other)
    assert sql(f"SELECT owner||':'||state FROM loot_entitlements WHERE encounter={n}")==f'{aid}:available'
    assert a.action(n) in ('target_dead','stale_target')
    a.pump(.1);b.pump(.1);assert first(a.inventory,4)==6 and first(b.inventory,4)==4
    assert first(a.inventory,2)==2 and first(b.inventory,2)==2
    print('two contributors, capped overkill, full bag, owner-only history: pass')
    last=n;n=npc(b,last);assert a.action(n)=='hit';a.logout();peers.remove(a)
    assert b.action(n)=='hit';committed(n)
    assert sql(f"SELECT reason||':'||awarded_xp FROM encounter_recipients WHERE encounter={n} AND character_id={aid}")=='1:0'
    assert first(status(b,n),3)==4
    a,ignored=connect('a',aid)
    last=n;n=npc(a,last);assert a.action(n)=='hit';a.logout();peers.remove(a);a,_=connect('a',aid)
    assert b.action(n)=='hit';committed(n);assert first(status(a,n),3)==6
    print('disconnect before freeze and reconnect before freeze: pass')
    # Delay commit briefly, disconnect after freeze, then recover through new session.
    # The locker holds the realm fence 0.4 s, under lock_timeout (800 ms): the
    # realm's own fenced work (the turbo authority read every 2 ticks, the
    # checkpoint) waits behind it and must not time out, or admission closes.
    # It ends with ROLLBACK, which flushes no WAL; its COMMIT took up to 738 ms
    # under local write load and, inferred, pushed the gate's hold past
    # lock_timeout (PQ-196).
    last=n;n=npc(a,last);assert a.action(n)=='hit'
    locker=subprocess.Popen(['docker','exec',name,'psql','-U','n3e','-d','n3e','-Atc',f"BEGIN; SELECT realm FROM realm_fence WHERE realm='{realm}' FOR UPDATE; SELECT pg_sleep(0.4); ROLLBACK;"],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    time.sleep(.1);assert b.action(n)=='hit';a.logout();peers.remove(a);locker.communicate(timeout=3);assert locker.returncode==0
    committed(n);a,_=connect('a',aid);assert first(status(a,n),3)==6
    old_entity=a.id;old_xp=first(a.inventory,4)
    print('disconnect after freeze preserves award without reviving old entity: pass')
    # XP/status has been observed over TLS; now kill the process without shutdown.
    server.kill();assert server.wait(timeout=6)==-9;server=None
    for peer in list(peers):peer.s.close();peers.remove(peer)
    time.sleep(3.1)  # Let the dead owner's database lease expire.
    start();a,_=connect('a',aid);assert a.id!=old_entity;assert first(a.inventory,4)==old_xp
    assert first(status(a,n),3)==6
    assert sql(f"SELECT state FROM loot_entitlements WHERE realm='{realm}' AND encounter={n}")=='available'
    print('server crash after acknowledgement and restart: immutable results, progression and entitlement recovered; no inventory claim: pass')
finally:
    for p in peers:
        try:p.s.close()
        except Exception:pass
    if server and server.poll() is None:server.terminate();server.wait(timeout=8)
    for log in logs:log.close()
    # PQ-128: each container's log, before it is removed.
    for c in containers:container_logs({name:'postgres',name+'-redis':'redis'}[c],['docker','logs','--timestamps',c])
    for container in reversed(containers):run('docker','rm','-f',container,good=False)
