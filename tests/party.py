"""Independent party-policy readers and hostile content bounds."""
import copy,json,os,shutil,struct,subprocess,sys,tempfile
from pathlib import Path
from party_live import prepare
sys.path.insert(0,str(Path('tools/assetc').resolve()))
import party
from common import u,string,digest

def check(out,good=True):
    hashes=[]
    for cmd in [['build/client/n3e-asset-check',str(out)],['target/debug/n3e-server','--check-content']]:
        p=subprocess.run(cmd,env={**os.environ,'N3E_PACKAGE':str(out)},text=True,capture_output=True)
        assert (p.returncode==0)==good,(cmd,p.stdout,p.stderr)
        if good:hashes.append(p.stdout.splitlines()[0])
    if good:assert hashes[0]==hashes[1]
for flags in ({},{'friends':False},{'full':True},{'alternate':True}):check(prepare(**flags))
full=prepare(full=True);m=json.loads((full/'recipe.json').read_text())['manifest'];p=m['party']
for key,values in [('capacity',[0,1,9,True]),('name_bytes',[0,25,False]),('level_gap',[-1,101,False]),('repeat_ticks',[-1,1201,True]),('level_minimum',[-1,1.1,float('nan')]),('level_maximum',[.9,11,float('inf')])]:
    for value in values:
        bad=copy.deepcopy(p);bad[key]=value
        try:party.cook(bad)
        except ValueError:pass
        else:raise AssertionError((key,value))
with tempfile.TemporaryDirectory(dir='build')as td:
    out=Path(td)/'release';shutil.copytree(full,out)
    files={p.name:p.read_bytes()for p in out.iterdir()if p.name not in('release.bin','release.sha256')}
    def repack(changed,engine=24,protocol=17):
        index=b'N3R1'+u(1)+u(engine)+u(protocol)+string(m['game_id'])+string(m['package_version'])+u(len(changed))
        for name,data in sorted(changed.items()):(out/name).write_bytes(data);index+=string(name)+u(len(data))+digest(data)
        (out/'release.bin').write_bytes(index)
    original=files['party.bin']
    for data in [b'BAD!'+original[4:],original[:-1],original+b'\0',original[:4]+u(9)+original[8:],original[:12]+struct.pack('<d',float('nan'))+original[20:],original[:20]+struct.pack('<d',.5)+original[28:]]:
        changed=dict(files);changed['party.bin']=data;repack(changed);check(out,False)
    for engine,protocol in [(23,17),(24,16),(25,18)]:repack(files,engine,protocol);check(out,False)
    for absent in ['party.bin','editing.bin','life.bin','progression.bin','inventory.bin','commerce.bin','equipment.bin','stats.bin','damage.bin','storage.bin']:
        changed=dict(files);del changed[absent];repack(changed);check(out,False)
    changed=dict(files);del changed['friends.bin'];repack(changed);check(out)
print('PASS party base/full/alternate/no-friends packages, bounded double policy, malformed source/cooked records and dependency rejection')
