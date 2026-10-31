"""Independent readers, source bounds and frozen award contracts."""
import copy,json,os,shutil,struct,subprocess,sys,tempfile
from pathlib import Path
from party_rewards_live import prepare
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
for key,values in [('bonus_tenths',[-1,9,True]),('level_gap',[-1,101,False]),('level_minimum',[-1,1.1,float('nan')]),('level_maximum',[.9,11,float('inf')]),('level_xp',[[200]*9,[0]*10,[2**31]*10,[201]+p['party_rewards']['level_xp'][1:]])]:
    for value in values:
        bad=copy.deepcopy(p);bad['party_rewards'][key]=value
        try:progression.cook(bad,m['gameplay'],m['game_id'])
        except ValueError:pass
        else:raise AssertionError((key,value))
with tempfile.TemporaryDirectory(dir='build')as td:
    out=Path(td)/'release';shutil.copytree(package,out)
    files={f.name:f.read_bytes()for f in out.iterdir()if f.name not in('release.bin','release.sha256')}
    def repack(changed,engine=25,protocol=18):
        index=b'N3R1'+u(1)+u(engine)+u(protocol)+string(m['game_id'])+string(m['package_version'])+u(len(changed))
        for name,data in sorted(changed.items()):(out/name).write_bytes(data);index+=string(name)+u(len(data))+digest(data)
        (out/'release.bin').write_bytes(index)
    original=files['progression.bin']
    for data in [b'N3P1'+original[4:],original[:-1],original+b'\0',original[:-64]+u(9)+original[-60:],original[:-60]+struct.pack('<d',float('nan'))+original[-52:],original[:-40]+u(201)+original[-36:]]:
        changed=dict(files);changed['progression.bin']=data;repack(changed);check(out,False)
    for absent in ['party.bin','progression.bin','editing.bin']:
        changed=dict(files);del changed[absent];repack(changed);check(out,False)
    for engine,wire in [(24,17),(25,17),(26,19)]:repack(files,engine,wire);check(out,False)
print('PASS party rewards original base/full/alternate packages, hostile caps/bonus/ratios, version and dependency rejection')
