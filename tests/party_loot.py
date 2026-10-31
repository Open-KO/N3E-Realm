"""N3P3 independent readers and hostile policy/compatibility checks."""
import copy,json,os,shutil,struct,subprocess,sys,tempfile
from pathlib import Path
from party_loot_live import prepare
sys.path.insert(0,str(Path('tools/assetc').resolve()))
import progression
from common import u,string,digest

def check(out,good=True):
    hashes=[]
    for cmd in [['build/client/n3e-asset-check',str(out)],['target/debug/n3e-server','--check-content']]:
        p=subprocess.run(cmd,env={**os.environ,'N3E_PACKAGE':str(out)},text=True,capture_output=True)
        assert (p.returncode==0)==good,(cmd,p.stdout,p.stderr)
        if good:hashes.append(p.stdout.splitlines()[0])
    if good:assert hashes[0]==hashes[1]
for flags in ({},{'full':True},{'alternate':True}):check(prepare(**flags))
package=prepare();m=json.loads((package/'recipe.json').read_text())['manifest'];p=m['progression']
for v in [0,101,True,1.5,float('nan')]:
    bad=copy.deepcopy(p);bad['party_loot']['radius']=v
    try:progression.cook(bad,m['gameplay'],m['game_id'])
    except ValueError:pass
    else:raise AssertionError(v)
with tempfile.TemporaryDirectory(dir='build')as td:
    out=Path(td)/'release';shutil.copytree(package,out)
    files={f.name:f.read_bytes()for f in out.iterdir()if f.name not in('release.bin','release.sha256')}
    def repack(changed,engine=26,protocol=19):
        index=b'N3R1'+u(1)+u(engine)+u(protocol)+string(m['game_id'])+string(m['package_version'])+u(len(changed))
        for name,data in sorted(changed.items()):(out/name).write_bytes(data);index+=string(name)+u(len(data))+digest(data)
        (out/'release.bin').write_bytes(index)
    original=files['progression.bin']
    for data in [b'N3P2'+original[4:],original[:-1],original+b'\0',original[:-4]+u(0),original[:-4]+u(101)]:
        changed=dict(files);changed['progression.bin']=data;repack(changed);check(out,False)
    for absent in ['party.bin','progression.bin','editing.bin']:
        changed=dict(files);del changed[absent];repack(changed);check(out,False)
    for engine,wire in [(25,18),(26,18),(27,20)]:repack(files,engine,wire);check(out,False)
print('PASS party loot base/full/alternate readers, hostile radius/trailing/version/dependency records')
