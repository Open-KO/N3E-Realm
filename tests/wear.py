"""Independent consumers, hostile rehashed durability definitions and reuse."""
import copy,json,os,shutil,subprocess,sys,tempfile
from pathlib import Path
from wear_live import prepare
package=prepare();sys.path.insert(0,str(Path('tools/assetc').resolve()))
import main,wear
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
for value in [0,-1,1.1,float('nan'),float('inf'),True]:
    p=copy.deepcopy(m['wear']);p['scale']=value
    try:wear.cook(p,m['equipment'])
    except ValueError:pass
    else:raise AssertionError(value)
for key,value in [('id','demo:item/unknown'),('attack_slots',[2]),('defense_slots',[16]),('attack_slots',[0,0]),('attack_slots',[True])]:
    p=copy.deepcopy(m['wear']);p['items'][0][key]=value
    try:wear.cook(p,m['equipment'])
    except ValueError:pass
    else:raise AssertionError((key,value))
with tempfile.TemporaryDirectory(dir='build')as td:
    out=Path(td)/'release';shutil.copytree(package,out)
    files={p.name:p.read_bytes()for p in out.iterdir()if p.name not in('release.bin','release.sha256')}
    def repack(data,engine=20,protocol=13,omit=False):
        changed=dict(files);changed['wear.bin']=data
        if omit:del changed['wear.bin']
        index=b'N3R1'+u(1)+u(engine)+u(protocol)+string(m['game_id'])+string(m['package_version'])+u(len(changed))
        for name,data in sorted(changed.items()):(out/name).write_bytes(data);index+=string(name)+u(len(data))+digest(data)
        (out/'release.bin').write_bytes(index)
    original=files['wear.bin'];offset=16+4+len(m['wear']['items'][0]['id'])
    for data in [b'BAD!'+original[4:],original[:-1],original+b'\0']:repack(data);check(out,False)
    for at,value in [(8,0x7ff80000),(8,0xbff00000),(12,0),(offset,1<<16),(offset+4,1<<2)]:
        b=bytearray(original);b[at:at+4]=u(value);repack(bytes(b));check(out,False)
    for engine,protocol in [(19,13),(20,12),(21,13)]:repack(original,engine,protocol);check(out,False)
    repack(original,omit=True);check(out,False)
    source=Path(td)/'source';shutil.copytree('build/ko-completion/wear/source',source)
    other=json.loads(json.dumps(m).replace('demo:','alternate:').replace('"game_id": "demo"','"game_id": "alternate"'));other['wear']['scale']=.025
    (source/'package.json').write_text(json.dumps(other));main.cook(source,out);check(out)
print('PASS wear producer/readers, masks, nonfinite coefficients, rehashed malformed files, version pairing and second namespace')
