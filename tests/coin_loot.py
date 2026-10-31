"""N3P4 independent reader compatibility and hostile coin policy records."""
import copy,json,os,shutil,struct,subprocess,sys,tempfile
from pathlib import Path
from coin_loot_live import prepare
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
package=prepare();check(package);check(prepare(alternate=True));check(prepare(full=True))
m=json.loads((package/'recipe.json').read_text())['manifest'];p=m['progression']
for k,v in [('base',-1),('base',2**31),('minimum_percent',101),('maximum_percent',69),('event_percent',32768),('party_bonus_percent',101),('maximum',32767),('overflow',32767),('pickup_bonus_percent',101),('bonus_cap',0),('currency','other:coin'),('base',True),('maximum_percent',float('nan'))]:
    bad=copy.deepcopy(p);bad['coins'][k]=v
    try:progression.cook(bad,m['gameplay'],m['game_id'])
    except ValueError:pass
    else:raise AssertionError((k,v))
with tempfile.TemporaryDirectory(dir='build')as td:
    out=Path(td)/'release';shutil.copytree(package,out)
    files={f.name:f.read_bytes()for f in out.iterdir()if f.name not in('release.bin','release.sha256')}
    def repack(changed,engine=27,protocol=20):
        index=b'N3R1'+u(1)+u(engine)+u(protocol)+string(m['game_id'])+string(m['package_version'])+u(len(changed))
        for name,data in sorted(changed.items()):(out/name).write_bytes(data);index+=string(name)+u(len(data))+digest(data)
        (out/'release.bin').write_bytes(index)
    original=files['progression.bin']
    for data in [b'N3P3'+original[4:],original[:-1],original+b'\0',original[:-4]+u(0),original[:-4]+u(32767),original[:-12]+u(32767)+original[-8:]]:
        changed=dict(files);changed['progression.bin']=data;repack(changed);check(out,False)
    for absent in ['inventory.bin','party.bin','progression.bin']:
        changed=dict(files);del changed[absent];repack(changed);check(out,False)
    for engine,wire in [(26,19),(27,19),(28,21)]:repack(files,engine,wire);check(out,False)
print('PASS coin drop base/alternate readers, hostile generation limits, missing dependencies, wire/version and malformed records')
