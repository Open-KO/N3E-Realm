"""Independent consumers, hostile rehashed durability definitions and reuse."""
import copy,json,os,shutil,subprocess,sys,tempfile
from pathlib import Path
from storage_live import prepare
package=prepare();sys.path.insert(0,str(Path('tools/assetc').resolve()))
import main,storage
from common import u,string,digest
m=json.loads((package/'recipe.json').read_text())['manifest']
def check(out,good=True):
    hashes=[]
    for cmd in [['build/client/n3e-asset-check',str(out)],['target/debug/n3e-server','--check-content']]:
        p=subprocess.run(cmd,env={**os.environ,'N3E_PACKAGE':str(out)},text=True,capture_output=True)
        assert(p.returncode==0)==good,(cmd,p.stdout,p.stderr)
        if good:hashes.append(p.stdout.splitlines()[0])
    if good:assert hashes[0]==hashes[1]
check(package)
for key,values in [('capacity',[0,193,True]),('coin_limit',[0,2100000001,True]),('services',[[],[{}]])]:
    for value in values:
        p=copy.deepcopy(m['storage']);p[key]=value
        try:storage.cook(p,m['game_id'])
        except (ValueError,TypeError):pass
        else:raise AssertionError((key,value))
for key,value in [('radius',float('nan')),('radius',0),('position',[float('inf'),0,0]),('remote',1),('open_fee',-1),('id','foreign:bank'),('label','bad\nlabel')]:
    p=copy.deepcopy(m['storage']);p['services'][0][key]=value
    try:storage.cook(p,m['game_id'])
    except ValueError:pass
    else:raise AssertionError((key,value))
with tempfile.TemporaryDirectory(dir='build')as td:
    out=Path(td)/'release';shutil.copytree(package,out)
    files={p.name:p.read_bytes()for p in out.iterdir()if p.name not in('release.bin','release.sha256')}
    def repack(data,engine=21,protocol=14,omit=False):
        changed=dict(files);changed['storage.bin']=data
        if omit:del changed['storage.bin']
        index=b'N3R1'+u(1)+u(engine)+u(protocol)+string(m['game_id'])+string(m['package_version'])+u(len(changed))
        for name,data in sorted(changed.items()):(out/name).write_bytes(data);index+=string(name)+u(len(data))+digest(data)
        (out/'release.bin').write_bytes(index)
    original=files['storage.bin'];service=m['storage']['services'][0]
    position=16+4+len(service['id'])+4+len(service['label'])
    for data in [b'BAD!'+original[4:],original[:-1],original+b'\0']:repack(data);check(out,False)
    for at,value in [(4,0),(4,193),(8,2100000001),(12,0),(position,0x7fc00000),(position+12,0),(position+16,2),(position+20,2100000001)]:
        b=bytearray(original);b[at:at+4]=u(value);repack(bytes(b));check(out,False)
    for engine,protocol in [(20,14),(21,13),(22,14)]:repack(original,engine,protocol);check(out,False)
    repack(original,omit=True);check(out,False)
    source=Path(td)/'source';shutil.copytree('build/ko-completion/storage/source',source)
    other=json.loads(json.dumps(m).replace('demo:','alternate:').replace('"game_id": "demo"','"game_id": "alternate"'));other['storage']['capacity']=24
    (source/'package.json').write_text(json.dumps(other));main.cook(source,out);check(out)
print('PASS account storage producer/readers, rehashed hostile bounds, version pairing and second namespace')
