"""Producer/independent readers reject hostile, correctly rehashed item policies."""
import copy,json,os,shutil,struct,subprocess,sys,tempfile
from pathlib import Path
from inventory_live import prepare
package=prepare()
sys.path.insert(0,str(Path('tools/assetc').resolve()))
import inventory,main
from common import u,string,digest
m=json.loads((package/'recipe.json').read_text())['manifest']; p=m['inventory']
def check(out,good=True):
    hashes=[]
    for cmd in [['build/client/n3e-asset-check',str(out)],['target/debug/n3e-server','--check-content']]:
        r=subprocess.run(cmd,env={**os.environ,'N3E_PACKAGE':str(out)},capture_output=True,text=True)
        assert (r.returncode==0)==good,(cmd,r.stdout,r.stderr)
        if good:hashes.append(r.stdout.splitlines()[0])
    if good:assert hashes[0]==hashes[1]
check(package)
for key,value in [('capacity',0),('capacity',65),('capacity',9),('capacity',True),('currency','foreign:coin'),('starting_currency',1000000001),('currency_limit',2**31),('items',[])]:
    bad=copy.deepcopy(p);bad[key]=value
    try:inventory.cook(bad,'demo',m['gameplay']['item'],m['gameplay']['slots'])
    except ValueError:pass
    else:raise AssertionError(key)
for key,value in [('label',''),('label','bad\nlabel'),('id','other:blade'),('starting',2),('stack_limit',0),('durability',65536)]:
    bad=copy.deepcopy(p);bad['items'][1][key]=value
    try:inventory.cook(bad,'demo',m['gameplay']['item'],8)
    except ValueError:pass
    else:raise AssertionError(key)
with tempfile.TemporaryDirectory(dir='build') as temp:
    out=Path(temp)/'release';shutil.copytree(package,out)
    files={p.name:p.read_bytes() for p in out.iterdir() if p.name not in ('release.bin','release.sha256')}
    def repack(data,engine=15,protocol=8,omit=False):
        changed=dict(files);changed['inventory.bin']=data
        if omit:del changed['inventory.bin']
        index=b'N3R1'+u(1)+u(engine)+u(protocol)+string(m['game_id'])+string(m['package_version'])+u(len(changed))
        for name,data in sorted(changed.items()):
            (out/name).write_bytes(data);index+=string(name)+u(len(data))+digest(data)
        (out/'release.bin').write_bytes(index)
    original=files['inventory.bin']
    for data in [original[:-1],original+b'\0',b'BAD!'+original[4:],original[:4]+u(0)+original[8:],original[:4]+u(9)+original[8:],original[:4]+u(65)+original[8:]]:
        repack(data);check(out,False)
    for engine,protocol in [(14,8),(15,7),(16,8)]:repack(original,engine,protocol);check(out,False)
    repack(original,omit=True);check(out,False)
    # Reward durability is constrained consistently in both readers.
    offset=8;offset+=4+struct.unpack_from('<I',original,offset)[0]+12
    for _ in range(2):offset+=4+struct.unpack_from('<I',original,offset)[0]
    altered=bytearray(original);altered[offset+4:offset+8]=u(1);repack(bytes(altered));check(out,False)
    source=Path(temp)/'source';shutil.copytree('build/ko-completion/items/source',source)
    alternate=json.dumps(m).replace('demo:','second:').replace('"game_id": "demo"','"game_id": "second"')
    (source/'package.json').write_text(alternate);other=Path(temp)/'second';main.cook(source,other);check(other)
print('PASS inventory producer, C++/Rust rehashed hostile policies, compatibility and second namespace with identical binaries')
