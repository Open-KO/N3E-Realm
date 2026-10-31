"""Two graphical clients share authoritative strikes/death/replacement; disposable lab."""
import json, os, re, subprocess, sys, time, uuid
from pathlib import Path
from world_peer import Peer
sys.path.insert(0,str(Path('tools/assetc').resolve()))
import animation_fixture, main
B=Path('build/ko-07');ko='--ko' in sys.argv
animation_fixture.cook(ko)
root=B/('source-ko' if ko else 'source')
m=json.loads((root/'package.json').read_text())
m['gameplay'].update(health=30,npc_health=20)
m['damage']['player'].update(attack=100,accuracy=10000)
m['damage']['npc'].update(attack=10,accuracy=10000)
# Fast but visible synthetic corpse/respawn; preserve authoritative life path.
m['life'].update(npc_corpse_ticks=60,npc_respawn_ticks=100)
(root/'package.json').write_text(json.dumps(m))
package=(B/('graphics-ko' if ko else 'graphics')).resolve();main.cook(root,package)
project='n3e-ko07-'+uuid.uuid4().hex[:8]
env={**os.environ,'N3E_PORT':'0','N3E_REALM':project,'N3E_PACKAGE_PATH':str(package),'N3E_UID':str(os.getuid()),'N3E_GID':str(os.getgid())}
password='test-only-'+uuid.uuid4().hex
base=['docker','compose','-p',project]
def dc(*args,stdin=None):
    p=subprocess.run(base+list(args),env=env,input=stdin,text=True,capture_output=True,timeout=180)
    assert p.returncode==0,(args,p.stdout,p.stderr)
    return p.stdout
processes=[];outputs=[]
try:
    dc('up','--build','-d','--wait')
    port=int(dc('port','server','7777').strip().rsplit(':',1)[1])
    for name in ['observer','actor']:
        dc('exec','-T','server','n3e-server','account-create',name,stdin=password+'\n')
        p=Peer(port,name,password,game=m['game_id'],protocol=3,content=(package/'release.sha256').read_text().strip())
        cid=p.create(name.title())
        if name=='observer':
            p.select(cid)
            for _ in range(20):p.move(0,1,mode=1);time.sleep(.055);p.until(10)
            p.logout()
        else:p.s.close()
        log=B/f'{package.name}-{name}.log';output=log.open('w');outputs.append(output)
        processes.append(subprocess.Popen(['build/client/n3e-test-client',str(package),'--connect',f'localhost:{port}','--ca','deploy/local/ca.pem','--auto-login','--world-smoke','42','--capture',str(B/f'{package.name}-{name}.ppm')],env={**env,'N3E_TEST_ACCOUNT':name,'N3E_TEST_PASSWORD':password,'N3E_TEST_ANIMATION':name,'N3E_TEST_FRAME_MS':'33' if name=='observer' else '7'},stdout=output,stderr=subprocess.STDOUT))
    for p in processes:assert p.wait(timeout=65)==0
    for output in outputs:output.close()
    logs={name:(B/f'{package.name}-{name}.log').read_text() for name in ['actor','observer']}
    for name,role in [('actor','local'),('observer','remote')]:
        states={int(v) for v in re.findall(r'ANIMATION role='+role+r' id=\d+ state=(\d+)',logs[name])}
        assert {0,2,3,4}<=states,(name,states,logs[name])
        npcstates={int(v) for v in re.findall(r'ANIMATION role=npc id=\d+ state=(\d+)',logs[name])}
        assert {0,1,2,3}<=npcstates,(name,npcstates,logs[name])
        ids=set(re.findall(r'ANIMATION role='+role+r' id=(\d+)',logs[name]));assert len(ids)>=2,(name,ids)
    def outcomes(log,role):
        return set(re.findall(r'ANIMATION role='+role+r' id=(\d+) state=2 strike=(\d+) hp=\d+',log))
    assert outcomes(logs['actor'],'local') & outcomes(logs['observer'],'remote')
    print('PASS',package.name,'two graphical clients: NPC idle/run/attack/death, local/remote shared strike, death, fresh respawn identity',flush=True)
finally:
    for p in processes:
        if p.poll() is None:p.terminate();p.wait(timeout=5)
    for output in outputs:output.close()
    (B/f'{package.name}-server.log').write_text(dc('logs','--no-color'))
    dc('down','-v','--remove-orphans')
