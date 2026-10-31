"""Independent equipment package readers and hostile rehashed definitions."""
import copy,json,os,shutil,struct,subprocess,sys,tempfile
from pathlib import Path
from equipment_live import prepare
package=prepare();sys.path.insert(0,str(Path('tools/assetc').resolve()))
import equipment,main
from common import u,string,digest
m=json.loads((package/'recipe.json').read_text())['manifest'];p=m['equipment']
def check(out,good=True):
    hashes=[]
    for cmd in [['build/client/n3e-asset-check',str(out)],['target/debug/n3e-server','--check-content']]:
        r=subprocess.run(cmd,env={**os.environ,'N3E_PACKAGE':str(out)},capture_output=True,text=True)
        assert (r.returncode==0)==good,(cmd,r.stdout,r.stderr)
        if good:hashes.append(r.stdout.splitlines()[0])
    if good:assert hashes[0]==hashes[1]
check(package)
for key,value in [('race',256),('race',True),('title',256),('attributes',[60]*4),('attributes',[256]*5),('slots',[]),('slots',['Same','Same']),('slots',['Bad\nname']),('items',[])]:
    bad=copy.deepcopy(p);bad[key]=value
    try:equipment.cook(bad,m['inventory'],m['game_id'])
    except ValueError:pass
    else:raise AssertionError(key)
for key,value in [('id','demo:item/potion'),('slots',[]),('slots',[16]),('slots',[0,0]),('blocks',[0]),('race',256),('title',256),('attributes',[-1]*5),('swappable',1)]:
    bad=copy.deepcopy(p);bad['items'][0][key]=value
    try:equipment.cook(bad,m['inventory'],m['game_id'])
    except ValueError:pass
    else:raise AssertionError(key)
with tempfile.TemporaryDirectory(dir='build') as td:
    out=Path(td)/'release';shutil.copytree(package,out)
    files={p.name:p.read_bytes() for p in out.iterdir() if p.name not in ('release.bin','release.sha256')}
    def repack(data,engine=18,protocol=11,omit=False):
        changed=dict(files);changed['equipment.bin']=data
        if omit:del changed['equipment.bin']
        index=b'N3R1'+u(1)+u(engine)+u(protocol)+string(m['game_id'])+string(m['package_version'])+u(len(changed))
        for name,data in sorted(changed.items()):(out/name).write_bytes(data);index+=string(name)+u(len(data))+digest(data)
        (out/'release.bin').write_bytes(index)
    original=files['equipment.bin']
    for data in [original[:-1],original+b'\0',b'BAD!'+original[4:]]:repack(data);check(out,False)
    for at,value in [(4,256),(8,256),(12,256),(32,0),(32,17)]:
        b=bytearray(original);b[at:at+4]=u(value);repack(bytes(b));check(out,False)
    at=36
    for slot in p['slots']:at+=4+len(slot)
    at+=4+4+len(p['items'][0]['id'])
    for offset,value in [(0,0),(0,1<<16),(4,1),(8,256),(12,256),(16,256),(36,2)]:
        b=bytearray(original);b[at+offset:at+offset+4]=u(value);repack(bytes(b));check(out,False)
    for engine,protocol in [(17,11),(18,10),(19,11)]:repack(original,engine,protocol);check(out,False)
    repack(original,omit=True);check(out,False)
    source=Path(td)/'source';shutil.copytree('build/ko-completion/equipment/source',source)
    other=json.loads(json.dumps(m).replace('demo:','second:').replace('"game_id": "demo"','"game_id": "second"'))
    other['equipment']['slots']=['Primary','Secondary','Band A','Band B'];other['equipment']['race']=3
    (source/'package.json').write_text(json.dumps(other));alternate=Path(td)/'second';main.cook(source,alternate);check(alternate)
print('PASS equipment producer and independent readers, slot masks, requirements, malformed rehashed policies, version pairing and second namespace')
