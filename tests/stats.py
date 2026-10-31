"""Independent high-precision vectors, readers, hostile data and namespace reuse."""
import copy,json,os,shutil,struct,subprocess,sys,tempfile
from pathlib import Path
from stats_live import prepare,oracle,decode_stats
from world_peer import fields
package=prepare();sys.path.insert(0,str(Path('tools/assetc').resolve()))
import main,stats
from common import u,string,digest
m=json.loads((package/'recipe.json').read_text())['manifest']
def run(cmd,out):
    p=subprocess.run(cmd,env={**os.environ,'N3E_PACKAGE':str(out)},text=True,capture_output=True)
    assert p.returncode==0,(cmd,p.stdout,p.stderr)
    return p.stdout

def check(out,good=True):
    hashes=[]
    for cmd in [['build/client/n3e-asset-check',str(out)],['target/debug/n3e-server','--check-content']]:
        p=subprocess.run(cmd,env={**os.environ,'N3E_PACKAGE':str(out)},text=True,capture_output=True)
        assert(p.returncode==0)==good,(cmd,p.stdout,p.stderr)
        if good:hashes.append(p.stdout.splitlines()[0])
    if good:assert hashes[0]==hashes[1]
check(package)
for key,value in [('primary',1),('primary',9),('secondary',0),('dual_wield',2),('attack_linear',float('nan')),('rate_scale',2),('broken_raw_divisor',0),('items',[])]:
    p=copy.deepcopy(m['stats']);p[key]=value
    try:stats.cook(p,m['inventory'],m['equipment'],m['game_id'])
    except ValueError:pass
    else:raise AssertionError(key)
with tempfile.TemporaryDirectory(dir='build')as td:
    source=Path(td)/'source';shutil.copytree('build/ko-completion/stats/source',source);out=Path(td)/'release'
    for variant in ['warrior','rogue','dagger','bow','mana','thresholds','second']:
        v=copy.deepcopy(m);p=v['stats']
        if variant=='rogue':p['dexterity_attack']=1
        if variant in ('dagger','bow'):
            for i in p['items'][:2]:i['category']='demo:weapon/'+variant;i['attack']=41
        if variant=='mana':p['mana']['coefficient']=.0013
        if variant=='thresholds':v['equipment']['attributes']=[180,130,75,55,50]
        if variant=='second':v=json.loads(json.dumps(v).replace('demo:','alternate:').replace('"game_id": "demo"','"game_id": "alternate"'))
        (source/'package.json').write_text(json.dumps(v));main.cook(source,out);check(out)
        output=run(['cargo','test','--locked','stats::tests::vectors','--','--ignored','--exact','--nocapture'],out);count=0
        for line in output.splitlines():
            if not line.startswith('VECTOR '):continue
            _,level,case,hexdata=line.split();level=int(level);case=int(case)
            records=[None]*len(v['equipment']['slots'])
            for slot,index in [(0,0),(1,1),(2,3)]:
                if case&(1<<slot):records[slot]=(v['equipment']['items'][index]['id'],0 if case&8 else 80)
            got=decode_stats(fields(bytes.fromhex(hexdata)));want=oracle(v,records,level)
            assert got==want,(variant,level,case,got,want)
            count+=1
        assert count==48,count
    # Rehashed hostile packages exercise both independent consumers.
    shutil.rmtree(out);shutil.copytree(package,out)
    files={p.name:p.read_bytes() for p in out.iterdir()if p.name not in('release.bin','release.sha256')}
    def repack(data,engine=19,protocol=12,omit=False):
        changed=dict(files);changed['stats.bin']=data
        if omit:del changed['stats.bin']
        index=b'N3R1'+u(1)+u(engine)+u(protocol)+string(m['game_id'])+string(m['package_version'])+u(len(changed))
        for name,data in sorted(changed.items()):(out/name).write_bytes(data);index+=string(name)+u(len(data))+digest(data)
        (out/'release.bin').write_bytes(index)
    original=files['stats.bin']
    for data in [original[:-1],original+b'\0',b'BAD!'+original[4:]]:repack(data);check(out,False)
    for at,value in [(4,1),(8,0),(12,2),(32,0),(56,0x7fc00000),(92,0x40000000)]:
        b=bytearray(original);b[at:at+4]=u(value);repack(bytes(b));check(out,False)
    for engine,protocol in [(18,12),(19,11),(20,12)]:repack(original,engine,protocol);check(out,False)
    repack(original,omit=True);check(out,False)
print('PASS 336 independent decimal stat vectors, broken items, dual/offhand, mana/stamina, level scaling, base thresholds, independent readers, hostile rehashed policies and namespace reuse')
