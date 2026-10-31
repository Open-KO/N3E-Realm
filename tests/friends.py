"""Friend capability isolation, independent readers and hostile dependency graphs."""
import copy,json,os,shutil,subprocess,sys,tempfile
from pathlib import Path
from friends_live import prepare
sys.path.insert(0,str(Path('tools/assetc').resolve()))
import main,friends
from common import u,string,digest

def check(out,good=True):
    hashes=[]
    for cmd in [['build/client/n3e-asset-check',str(out)],['target/debug/n3e-server','--check-content']]:
        p=subprocess.run(cmd,env={**os.environ,'N3E_PACKAGE':str(out)},text=True,capture_output=True)
        assert (p.returncode==0)==good,(cmd,p.stdout,p.stderr)
        if good:hashes.append(p.stdout.splitlines()[0])
    if good:assert hashes[0]==hashes[1]
base=prepare();check(base)
assert not (base/'inventory.bin').exists() and not (base/'storage-auth.bin').exists()
alternate=prepare(alternate=True);check(alternate)
full=prepare(full=True);check(full)
m=json.loads((full/'recipe.json').read_text())['manifest'];p=m['friends']
for key,values in [('capacity',[0,25,True]),('name_bytes',[0,25,False]),('refresh_ticks',[0,1201,True])]:
    for value in values:
        bad=copy.deepcopy(p);bad[key]=value
        try:friends.cook(bad)
        except ValueError:pass
        else:raise AssertionError((key,value))
with tempfile.TemporaryDirectory(dir='build')as td:
    out=Path(td)/'release';shutil.copytree(full,out)
    files={p.name:p.read_bytes()for p in out.iterdir()if p.name not in('release.bin','release.sha256')}
    def repack(changed,engine=23,protocol=16):
        index=b'N3R1'+u(1)+u(engine)+u(protocol)+string(m['game_id'])+string(m['package_version'])+u(len(changed))
        for name,data in sorted(changed.items()):(out/name).write_bytes(data);index+=string(name)+u(len(data))+digest(data)
        (out/'release.bin').write_bytes(index)
    original=files['friends.bin']
    for data in [b'BAD!'+original[4:],original[:-1],original+b'\0',b'N3F1'+u(25)+u(20)+u(60),b'N3F1'+u(24)+u(25)+u(60),b'N3F1'+u(24)+u(20)+u(0)]:
        changed=dict(files);changed['friends.bin']=data;repack(changed);check(out,False)
    for engine,protocol in [(22,16),(23,15),(24,17)]:repack(files,engine,protocol);check(out,False)
    for absent in ['friends.bin','editing.bin','life.bin','progression.bin','inventory.bin','commerce.bin','repair.bin','equipment.bin','stats.bin','damage.bin','wear.bin','storage.bin']:
        changed=dict(files);del changed[absent];repack(changed);check(out,False)
    # Protection is optional in a newer friend-enabled item package.
    changed=dict(files);del changed['storage-auth.bin'];repack(changed);check(out)
    # Every valid prefix of the optional item chain works without unrelated successors.
    ordered=['inventory.bin','commerce.bin','repair.bin','equipment.bin','stats.bin','wear.bin','storage.bin','storage-auth.bin']
    for count in range(len(ordered)):
        changed={k:v for k,v in files.items()if k not in ordered[count:]}
        if count<=4:
            import struct
            progression=bytearray(changed['progression.bin']);progression[8:12]=u(1);changed['progression.bin']=bytes(progression)
        repack(changed);check(out)
print('PASS independent friend base/full/alternate packages, all optional item prefixes, malformed files, bounds, versions and missing dependencies')
