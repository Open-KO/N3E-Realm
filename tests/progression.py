"""Original N3P1 producer, rehashed hostile releases and independent golden vectors."""
import copy
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path('tools/assetc').resolve()))
import progression
import progression_fixture
from common import u,string,digest
package=progression_fixture.cook()
m=json.loads((package/'recipe.json').read_text())['manifest']
p=m['progression'];g=m['gameplay']

def check(out,good=True):
    hashes=[]
    for command in [['build/client/n3e-asset-check',str(out)],['target/debug/n3e-server','--check-content']]:
        r=subprocess.run(command,env={**os.environ,'N3E_PACKAGE':str(out)},capture_output=True,text=True)
        assert (r.returncode==0)==good,(command,r.stdout,r.stderr)
        if good:hashes.append(r.stdout.splitlines()[0])
    if good:assert hashes[0]==hashes[1]
check(package)
for key,value in [('thresholds',[0]*10),('thresholds',[0,20,50,90,140,200,270,350,440,2**63]),('model','unknown'),('stat_policy','heal'),('capacity',3),('npc_level',11),('radius',float('nan')),('ttl',9),('origin','authentic')]:
    bad=copy.deepcopy(p);bad[key]=value
    try:progression.cook(bad,g,m['game_id'])
    except ValueError:pass
    else:raise AssertionError(key)
with tempfile.TemporaryDirectory(dir='build') as temp:
    out=Path(temp)/'release';shutil.copytree(package,out)
    files={p.name:p.read_bytes() for p in out.iterdir() if p.name not in ('release.bin','release.sha256')}
    def repack(data,engine=9,protocol=4,omit=False):
        changed=dict(files);changed['progression.bin']=data
        if omit:del changed['progression.bin']
        index=b'N3R1'+u(1)+u(engine)+u(protocol)+string(m['game_id'])+string(m['package_version'])+u(len(changed))
        for name,data in sorted(changed.items()):
            (out/name).write_bytes(data);index+=string(name)+u(len(data))+digest(data)
        (out/'release.bin').write_bytes(index)
    original=files['progression.bin']
    for data in [original[:-1],original+b'\0',b'BAD!'+original[4:],original[:4]+u(2)+original[8:]]:
        repack(data);check(out,False)
    # Locate cumulative thresholds independently from the format.
    at=12
    for _ in range(4):n=struct.unpack_from('<I',original,at)[0];at+=4+n
    at+=4
    for offset,data in [(at,struct.pack('<Q',1)),(at+8,struct.pack('<Q',0)),(at+72,struct.pack('<Q',2**63)),(at+80,u(3)),(at+88,u(11)),(at+96,struct.pack('<f',float('nan'))),(at+104,u(601))]:
        b=bytearray(original);b[offset:offset+len(data)]=data;repack(bytes(b));check(out,False)
    for e,v in [(8,4),(9,3),(10,4)]:repack(original,e,v);check(out,False)
    repack(original,omit=True);check(out,False)
# Ordinary startup must reject even before reaching dependency setup.
r=subprocess.run(['target/debug/n3e-server'],env={**os.environ,'N3E_PACKAGE':str(package),'N3E_TEST_PROGRESSION':'','N3E_REALM':'test-inactive'},capture_output=True)
assert r.returncode and b'contribution policy inactive' in r.stderr,r.stderr
Path('build/check').mkdir(parents=True,exist_ok=True)
for kind,exe in [('cpp','build/client/n3e-peer'),('rust','target/debug/n3e-server')]:
    subprocess.run([exe,'--golden','build/check/'+kind],check=True)
assert Path('build/check/cpp-settlement.bin').read_bytes()==Path('build/check/rust-settlement.bin').read_bytes()==bytes.fromhex(Path('protocol/golden-settlement.hex').read_text())
print('PASS progression producer, both hashed readers, compatibility, inactive gate, C++/Rust settlement golden')
