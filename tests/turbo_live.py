"""Two ordinary TLS clients against a disposable native server and PG/Redis."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid
import shutil
from world_peer import Peer,first,integer,blob,fields,real
sys.path.insert(0,str(Path('tools/assetc').resolve()))
import main
from readiness import free_ports, wait_postgres
from isolation import DISPOSABLE_POSTGRES, container_logs
B=Path('build/kx/turbo-live');B.mkdir(parents=True,exist_ok=True)
package=Path(os.environ.get('N3E_KO_WORK','build'),'packages/moradon').resolve()
name='n3e-turbo-'+uuid.uuid4().hex[:10];realm='test-'+name
protocol=json.loads((package/'recipe.json').read_text())['manifest']['protocol_version']
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
    p=Peer(listen,account,password,content=(package/'release.sha256').read_text().strip(),protocol=protocol)
    peers.append(p)
    if id is None:id=p.create(account.upper())
    assert p.select(id)[0]==10
    p.pump(.15)
    return p,id

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
    for container,image,container_port,extra in [(name,'postgres:17.4-bookworm@sha256:304ab813518754228f9f792f79d6da36359b82d8ecf418096c636725f8c930ad',5432,['-e','POSTGRES_USER=n3e','-e','POSTGRES_PASSWORD=test-only','-e','POSTGRES_DB=n3e',*DISPOSABLE_POSTGRES]),(name+'-redis','redis:7.4.2-bookworm@sha256:fbdbaea47b9ae4ecc2082ecdb4e1cea81e32176ffb1dcf643d422ad07427e5d9',6379,[])]:
        run('docker','run','--rm','-d','--name',container,*extra,'-p',f'127.0.0.1:{port()}:{container_port}',image);containers.append(container)
    pg=wait_postgres(name)
    redis=run('docker','port',name+'-redis','6379').stdout.strip();listen,health=free_ports(2)
    env.update(DATABASE_URL=f'host=127.0.0.1 port={pg} user=n3e password=test-only dbname=n3e',REDIS_ADDRESS=redis,N3E_REALM=realm,N3E_TEST_PROGRESSION='disposable',N3E_PACKAGE=str(package),N3E_LISTEN=f'127.0.0.1:{listen}',N3E_HEALTH=f'127.0.0.1:{health}')
    # wait_postgres proved the host path ready: any migration error is real.
    run('target/debug/n3e-server','migrate')
    run('target/debug/n3e-server','convert-progression')
    run('target/debug/n3e-server','account-create','a',stdin=password+'\n')
    start();a,aid=connect('a')
    def snapshot():
        a.send(14)
        return a.until(10)[1]
    def permission(allowed):
        for _ in range(40):
            w=snapshot()
            if bool(first(w,11))==allowed:return w
            time.sleep(.05)
        raise AssertionError(('permission',allowed,w))
    def move(generation,held=True,entity=None,expect=False):
        for attempt in range(12):
            a.seq+=1
            a.send(9,integer(1,a.session)+integer(2,a.seq)+real(3,1)+real(4,0)+integer(5,1)+integer(6,int(held))+integer(7,a.id if entity is None else entity)+integer(8,generation))
            for _ in range(20):
                w=snapshot();e=a.entities[a.id]
                if first(e,6)>=a.seq:break
            if bool(first(e,19))==expect:return w,e
        raise AssertionError(('turbo state',expect,w,e))
    w=permission(False)
    _,e=move(first(w,12))
    assert not first(e,19),e
    role('a',aid,'movement.turbo')
    w=permission(True);generation=first(w,12)
    w,e=move(generation,expect=True)
    assert first(e,19)==1,e
    assert abs(first(w,7)-45)<1e-5,e
    w,e=move(generation,False)
    assert not first(e,19) and abs(first(w,7)-4.5)<1e-5,e
    _,e=move(generation-1)
    assert not first(e,19),e
    role('a',aid,'movement.turbo',False)
    w=permission(False)
    assert first(w,12)>generation
    _,e=move(generation)
    assert not first(e,19),e
    role('a',aid,'movement.turbo')
    w=permission(True)
    _,e=move(first(w,12),expect=True)
    assert first(e,19),e
    time.sleep(.3);snapshot()
    assert not first(a.entities[a.id],19)
    run('docker','pause',name)
    try:
        time.sleep(.65)
        w=permission(False)
        assert not first(w,11)
    finally:run('docker','unpause',name)
    permission(True)
    print('PASS permission lease expires while PostgreSQL is paused, then recovers')
    if os.environ.get('N3E_TURBO_GRAPHICS')=='1':
        run('target/debug/n3e-server','account-create','b',stdin=password+'\n')
        b,bid=connect('b')
        import threading
        observer=threading.Thread(target=b.pump,args=(5,));observer.start()
        a.logout()
        window_args=['--fixed-window',os.environ['N3E_TEST_WINDOW_SIZE']] if os.environ.get('N3E_TEST_WINDOW_SIZE') else []
        result=subprocess.run(['build/client/n3e-test-client',str(package),'--connect',f'localhost:{listen}','--ca','deploy/local/ca.pem','--auto-login','--world-smoke','5' if os.environ.get('N3E_TEST_ANIMATION') else '3','--capture',str(B/'connected.ppm')]+window_args,env={**env,'N3E_TEST_ACCOUNT':'a','N3E_TEST_PASSWORD':password},capture_output=True,text=True,timeout=30)
        observer.join()
        (B/'graphics.log').write_text(result.stdout+result.stderr)
        assert result.returncode==0,(result.stdout,result.stderr)
        if window_args:
            with (B/'connected.ppm').open('rb') as capture:
                assert capture.readline()==b'P6\n'
                assert capture.readline().decode().strip().replace(' ','x')==window_args[1]
            print('PASS Moradon fixed drawable',window_args[1])
        if os.environ.get('N3E_TEST_WORLD_SAMPLING'):
            assert 'PASS world sampling matched-camera repeat/mirror captures' in result.stdout, result.stdout
        if os.environ.get('N3E_TEST_HUD'):
            assert 'PASS HUD graphical' in result.stdout,result.stdout
        if os.environ.get('N3E_TEST_ANIMATION') == 'actor':
            import re
            states=[int(v) for v in re.findall(r'ANIMATION role=local id=\d+ state=(\d+)',result.stdout)]
            assert len(states)>=3 and states[0]==0 and states[-1]==0 and any(s in (1,4,5) for s in states),result.stdout
            print('PASS Moradon graphical animation locomotion to idle and smooth-stop invariant')
    print(f'PASS real Moradon wire{protocol}: forged turbo denied, live grant, 45m/s authoritative speed, release, stale generation, acknowledged revocation, regrant, no-input reset')
finally:
    for p in peers:
        try:p.s.close()
        except Exception:pass
    if server is not None and server.poll() is None:server.kill();server.wait()
    for f in logs:f.close()
    # PQ-128: each container's log, before it is removed.
    for c in containers:container_logs({name:'postgres',name+'-redis':'redis'}[c],['docker','logs','--timestamps',c])
    for c in reversed(containers):run('docker','rm','-f',c,good=False)
