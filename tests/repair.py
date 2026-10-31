"""Binary-parameter curve, independent decimal goldens and hostile policies."""
import copy,json,os,shutil,struct,subprocess,sys,tempfile
from decimal import Decimal,localcontext
from pathlib import Path
from repair_live import prepare
package=prepare();sys.path.insert(0,str(Path('tools/assetc').resolve()))
import repair,main
from common import u,string,digest
m=json.loads((package/'recipe.json').read_text())['manifest'];p=m['repair']
def check(out,good=True):
    hashes=[]
    for cmd in [['build/client/n3e-asset-check',str(out)],['target/debug/n3e-server','--check-content']]:
        r=subprocess.run(cmd,env={**os.environ,'N3E_PACKAGE':str(out)},capture_output=True,text=True)
        assert (r.returncode==0)==good,(cmd,r.stdout,r.stderr)
        if good:hashes.append(r.stdout.splitlines()[0])
    if good:assert hashes[0]==hashes[1]
def quote(out,price,current,maximum,expected):
    for cmd in [['build/client/n3e-asset-check',str(out),'--repair-cost'],['target/debug/n3e-server','--repair-cost']]:
        r=subprocess.run(cmd+list(map(str,(price,current,maximum))),env={**os.environ,'N3E_PACKAGE':str(out)},capture_output=True,text=True)
        if expected is None:assert r.returncode,(cmd,r.stdout)
        else:assert r.returncode==0 and int(r.stdout)==expected,(cmd,r.stdout,r.stderr,expected)
check(package)
vectors=[(120,10,80,44),(120,79,80,0),(100000,0,10000,12599),(2147483647,0,65535,45108147),(1,0,2,0),(120,80,80,0)]
# Independent high-precision evaluation uses the exact constants recovered from memory.
linear=struct.unpack('<f',bytes.fromhex('17b7d138'))[0]
with localcontext() as ctx:
    ctx.prec=60
    for price,current,maximum,expected in vectors:
        computed=((Decimal(price)-10)*Decimal(linear)+Decimal(price)**Decimal(.82))*Decimal(maximum-current)/maximum
        assert int(computed)==expected
        quote(package,price,current,maximum,expected)
for a in [(120,81,80),(120,0,1),(120,0,0)]:quote(package,*a,None)
for key,value in [('power',float('nan')),('power',0),('power',1.1),('linear',-1),('offset',True),('offset',1000001),('multiplier',1.1),('items',['demo:item/potion'])]:
    bad=copy.deepcopy(p);bad[key]=value
    try:repair.cook(bad,m['inventory'])
    except ValueError:pass
    else:raise AssertionError(key)
with tempfile.TemporaryDirectory(dir='build') as td:
    out=Path(td)/'release';shutil.copytree(package,out)
    files={p.name:p.read_bytes() for p in out.iterdir() if p.name not in ('release.bin','release.sha256')}
    def repack(data,engine=17,protocol=10,omit=False):
        changed=dict(files);changed['repair.bin']=data
        if omit:del changed['repair.bin']
        index=b'N3R1'+u(1)+u(engine)+u(protocol)+string(m['game_id'])+string(m['package_version'])+u(len(changed))
        for name,data in sorted(changed.items()):(out/name).write_bytes(data);index+=string(name)+u(len(data))+digest(data)
        (out/'release.bin').write_bytes(index)
    original=files['repair.bin']
    for data in [original[:-1],original+b'\0',b'BAD!'+original[4:]]:repack(data);check(out,False)
    for at,data in [(4,struct.pack('<d',float('nan'))),(4,struct.pack('<d',1.01)),(12,struct.pack('<f',-1)),(16,u(1000001)),(20,struct.pack('<f',1.1)),(24,u(0))]:
        b=bytearray(original);b[at:at+len(data)]=data;repack(bytes(b));check(out,False)
    for engine,protocol in [(16,10),(17,9),(18,10)]:repack(original,engine,protocol);check(out,False)
    repack(original,omit=True);check(out,False)
    source=Path(td)/'source';shutil.copytree('build/ko-completion/repair/source',source)
    other=json.loads(json.dumps(m).replace('demo:','second:').replace('"game_id": "demo"','"game_id": "second"'));other['repair']['multiplier']=.5
    (source/'package.json').write_text(json.dumps(other));alternate=Path(td)/'second';main.cook(source,alternate);check(alternate)
    for price,current,maximum,expected in vectors:quote(alternate,price,current,maximum,expected//2)
    other['repair']['multiplier']=.7
    (source/'package.json').write_text(json.dumps(other));fractional=Path(td)/'fractional';main.cook(source,fractional);check(fractional)
    # A single final truncation would charge 1; truncating the base first charges 0.
    quote(fractional,2,15,80,0)
    quote(fractional,120,10,80,30)
print('PASS repair binary constants, decimal goldens, C++/Rust quotes, two-stage discount truncation, hostile policies and second namespace')
