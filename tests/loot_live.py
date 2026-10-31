"""Two ordinary TLS clients against a disposable native server and PG/Redis."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid
from world_peer import Peer,first,integer,blob,fields
sys.path.insert(0,str(Path('tools/assetc').resolve()))
import loot_fixture,main
from readiness import free_ports, wait_postgres
from isolation import DISPOSABLE_POSTGRES, container_logs
B=Path('build/ko-10');B.mkdir(parents=True,exist_ok=True)
loot_fixture.cook()
root=Path('build/loot-source');m=json.loads((root/'package.json').read_text());m['progression']['ttl']=10
(root/'package.json').write_text(json.dumps(m));package=(B/'live-package').resolve();main.cook(root,package)
name='n3e-ko10-live-'+uuid.uuid4().hex[:10];realm='test-'+name
password='test-only-'+uuid.uuid4().hex
containers=[];peers=[];server=None;logs=[];graphics=[]
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
    server=subprocess.Popen(['target/debug/n3e-server'],env={k:v for k,v in env.items() if k!='N3E_TEST_PROGRESSION'},stdout=f,stderr=f)
    for _ in range(100):
        assert server.poll() is None,Path(f.name).read_text()
        try:
            import urllib.request
            if urllib.request.urlopen(f'http://127.0.0.1:{health}/ready',timeout=.2).status==200:return
        except Exception:time.sleep(.05)
    raise AssertionError('server not ready')
def connect(account,id=None):
    p=Peer(listen,account,password,content=(package/'release.sha256').read_text().strip(),protocol=5)
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
    def page(p):
        p.send(23);tag,data=p.until(24,4);assert tag==24;return [fields(x) for x in data.get(1,[])]
    def claim(p,d,**overrides):
        seq=getattr(p,'claim_seq',0)+1;p.claim_seq=seq
        v=dict(session=p.session,seq=seq,entity=p.id,operation=first(d,1),encounter=first(d,2),item=first(d,3),quantity=1);v.update(overrides)
        p.send(25,integer(1,v['session'])+integer(2,v['seq'])+integer(3,v['entity'])+integer(4,v['operation'])+integer(5,v['encounter'])+blob(6,v['item'])+integer(7,v['quantity']))
        for _ in range(10):
            tag,result=p.until(26,4);assert tag==26
            if first(result,2)!=b'pending':return result
        raise AssertionError('claim remained pending')
    n=npc(a);assert a.action(n)=='hit';assert b.action(n)=='hit';assert committed(n)=='entitled'
    d=page(a)[0];assert page(b)==[] and page(other)==[]
    assert first(claim(other,d),2)==b'unknown'
    assert first(claim(a,d,entity=a.id+100),2)==b'stale_entity'
    assert first(claim(a,d,session=a.session+1),2)==b'stale_session'
    assert first(claim(a,d,item=b'forged:item'),2)==b'conflict'
    other.logout();peers.remove(other)
    # Entitlement is independent of NPC lifetime and survives process replacement.
    old_entity=a.id;old_xp=first(status(a,n),4)
    server.kill();assert server.wait(timeout=6)==-9;server=None
    for peer in list(peers):peer.s.close();peers.remove(peer)
    time.sleep(3.1);start();a,_=connect('a',aid);b,_=connect('b',bid)
    assert a.id!=old_entity and first(a.inventory,4)==old_xp
    assert first(page(a)[0],1)==first(d,1)
    result=claim(a,d);assert first(result,2)==b'claimed' and first(result,3)==1
    assert claim(a,d)==result
    a.send(27,integer(1,first(d,1)));assert a.until(26,4)[1]==result
    print('TLS owner discovery, stale/forged denial, S-to-C restart and duplicate/lost-result recovery: pass')
    server.kill();server.wait(timeout=6);server=None
    for peer in list(peers):peer.s.close();peers.remove(peer)
    time.sleep(3.1);start();a,_=connect('a',aid);assert first(a.inventory,2)==1 and first(a.inventory,4)==old_xp
    a.send(27,integer(1,first(d,1)));assert a.until(26,4)[1]==result
    print('TLS claim acknowledgement followed by SIGKILL: count/result/XP recovered exactly: pass')
    b,_=connect('b',bid)
    n=npc(a);assert a.action(n)=='hit';assert b.action(n)=='hit';committed(n)
    d2=page(a)[0];assert first(claim(a,d2),2)==b'claimed'
    previous=n;n=npc(a,previous);assert a.action(n)=='hit';assert b.action(n)=='hit';committed(n)
    d3=page(a)[0];xp=first(status(a,n),4)
    assert first(claim(a,d3),2)==b'inventory_full_not_committed'
    assert sql(f"SELECT state FROM loot_entitlements WHERE claim_operation={first(d3,1)}")=='available'
    assert sql(f"SELECT count(*) FROM loot_claim_results WHERE claim_operation={first(d3,1)}")=='0'
    server.kill();server.wait(timeout=6);server=None
    for peer in list(peers):peer.s.close();peers.remove(peer)
    time.sleep(10.2);start();a,_=connect('a',aid)
    assert first(a.inventory,2)==2 and first(a.inventory,4)==xp and page(a)==[]
    for _ in range(30):
        a.send(27,integer(1,first(d3,1)));r=a.until(26,4)[1]
        if first(r,2)==b'expired':break
        a.pump(.1)
    assert first(r,2)==b'expired'
    a.logout();peers.remove(a)
    print('full bag retains kill XP; server-down expiry recovers a single expired result, no inventory mutation: pass')
    # N3E_GRAPHICAL=1 is how tests/live.py (make live, the gate) selects every
    # suite's graphical branch (PQ-116); --graphical keeps the direct invocation.
    if '--graphical' in sys.argv or os.environ.get('N3E_GRAPHICAL')=='1':
        # Two actual rendered clients use the normal R and F keyboard handlers.
        for account in ['actor','observer']:
            run('target/debug/n3e-server','account-create',account,stdin=password+'\n')
            peer,cid=connect(account);peer.logout();peers.remove(peer)
        for account in ['actor','observer']:
            log=open(B/f'graphics-{account}.log','w');logs.append(log)
            graphics.append(subprocess.Popen(['build/client/n3e-test-client',str(package),'--connect',f'localhost:{listen}','--ca','deploy/local/ca.pem','--auto-login','--world-smoke','18','--capture',str(B/f'graphics-{account}.ppm')],env={**env,'N3E_TEST_ACCOUNT':account,'N3E_TEST_PASSWORD':password,'N3E_TEST_LOOT':account},stdout=log,stderr=subprocess.STDOUT))
        for client in graphics:assert client.wait(timeout=30)==0
        print('two graphical clients: shared kill XP, owner drop and keyboard claim/result/inventory: pass')
    if '--play' in sys.argv:
        for account in ['player1','player2']:
            run('target/debug/n3e-server','account-create',account,stdin=password+'\n')
            peer,cid=connect(account);peer.logout();peers.remove(peer)
            log=open(B/f'play-{account}.log','w');logs.append(log)
            graphics.append(subprocess.Popen(['build/client/n3e-test-client',str(package),'--connect',f'localhost:{listen}','--ca','deploy/local/ca.pem','--auto-login'],env={**env,'N3E_TEST_ACCOUNT':account,'N3E_TEST_PASSWORD':password},stdout=log,stderr=subprocess.STDOUT))
        print('Play: Z targets, R strikes, F claims nearest; close both windows to remove the disposable stack.',flush=True)
        for client in graphics:client.wait()


finally:
    for client in graphics:
        if client.poll() is None:client.terminate();client.wait(timeout=5)
    for p in peers:
        try:p.s.close()
        except Exception:pass
    if server and server.poll() is None:server.terminate();server.wait(timeout=8)
    for log in logs:log.close()
    # PQ-128: each container's log, before it is removed.
    for c in containers:container_logs({name:'postgres',name+'-redis':'redis'}[c],['docker','logs','--timestamps',c])
    for container in reversed(containers):run('docker','rm','-f',container,good=False)
