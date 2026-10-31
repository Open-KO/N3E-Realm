"""Independent commerce producer/readers, exact wire and malicious package tests."""
import copy,json,os,shutil,struct,subprocess,sys,tempfile
from pathlib import Path
from commerce_live import prepare
from world_peer import integer,blob
package=prepare();sys.path.insert(0,str(Path('tools/assetc').resolve()))
import commerce,main
from common import u,string,digest
m=json.loads((package/'recipe.json').read_text())['manifest'];p=m['commerce']
def check(out,good=True):
    hashes=[]
    for cmd in [['build/client/n3e-asset-check',str(out)],['target/debug/n3e-server','--check-content']]:
        r=subprocess.run(cmd,env={**os.environ,'N3E_PACKAGE':str(out)},capture_output=True,text=True)
        assert (r.returncode==0)==good,(cmd,r.stdout,r.stderr)
        if good:hashes.append(r.stdout.splitlines()[0])
    if good:assert hashes[0]==hashes[1]
check(package)
for key,value in [('weight_limit',0),('max_quantity',10000),('bulk_quantity',0),('bulk_price',2**31),('shops',[]),('items',[])]:
    bad=copy.deepcopy(p);bad[key]=value
    try:commerce.cook(bad,'demo',m['inventory'],m['gameplay']['item'])
    except ValueError:pass
    else:raise AssertionError(key)
for key,value in [('radius',float('nan')),('radius',21),('position',[0,0,1001]),('remote_sell',1),('items',['demo:item/token']),('id','other:shop/a'),('label',''),('label','bad\nlabel')]:
    bad=copy.deepcopy(p);bad['shops'][0][key]=value
    try:commerce.cook(bad,'demo',m['inventory'],m['gameplay']['item'])
    except ValueError:pass
    else:raise AssertionError(key)
with tempfile.TemporaryDirectory(dir='build') as td:
    out=Path(td)/'release';shutil.copytree(package,out)
    files={p.name:p.read_bytes() for p in out.iterdir() if p.name not in ('release.bin','release.sha256')}
    def repack(data,engine=16,protocol=9,omit=False):
        changed=dict(files);changed['commerce.bin']=data
        if omit:del changed['commerce.bin']
        index=b'N3R1'+u(1)+u(engine)+u(protocol)+string(m['game_id'])+string(m['package_version'])+u(len(changed))
        for name,data in sorted(changed.items()):(out/name).write_bytes(data);index+=string(name)+u(len(data))+digest(data)
        (out/'release.bin').write_bytes(index)
    original=files['commerce.bin']
    for data in [original[:-1],original+b'\0',b'BAD!'+original[4:]]:
        repack(data);check(out,False)
    for at,value in [(4,0),(8,10000),(12,2**31),(16,0),(20,4)]:
        b=bytearray(original);b[at:at+4]=u(value);repack(bytes(b));check(out,False)
    for engine,protocol in [(15,9),(16,8),(17,9)]:repack(original,engine,protocol);check(out,False)
    repack(original,omit=True);check(out,False)
    source=Path(td)/'source';shutil.copytree('build/ko-completion/commerce/source',source)
    alternate=json.dumps(m).replace('demo:','second:').replace('"game_id": "demo"','"game_id": "second"')
    (source/'package.json').write_text(alternate);out2=Path(td)/'second';main.cook(source,out2);check(out2)
expected=blob(32,integer(1,2)+blob(2,'buy-1')+integer(3,127)+integer(4,2)+blob(7,'fixture:shop/supplies')+blob(8,'fixture:item/potion')+integer(9,3))
assert bytes.fromhex(Path('protocol/golden-commerce.hex').read_text())==expected
for label,binary in [('cpp','build/client/n3e-peer'),('rust','target/debug/n3e-server')]:
    stem='build/ko-completion/commerce/'+label;subprocess.run([binary,'--golden',stem],check=True)
    assert Path(stem+'-commerce.bin').read_bytes()==expected
print('PASS commerce producer, both rehashed hostile readers, compatibility, independent golden and second namespace')
