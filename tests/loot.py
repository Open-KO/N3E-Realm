"""KO-10 release compatibility and independent cross-language wire/payload vectors."""
import os
from pathlib import Path
import struct
import subprocess
import sys
sys.path.insert(0,str(Path('tools/assetc').resolve()))
from world_peer import integer,blob
import loot_fixture,main,json,shutil,tempfile
from common import u,string,digest
package=loot_fixture.cook()
hashes=[]
for cmd in [['build/client/n3e-asset-check',str(package)],['target/debug/n3e-server','--check-content']]:
    p=subprocess.run(cmd,env={**os.environ,'N3E_PACKAGE':str(package)},capture_output=True,text=True)
    assert p.returncode==0,p.stderr
    hashes.append(p.stdout.splitlines()[0])
assert hashes[0]==hashes[1]
expected=blob(25,integer(1,63)+integer(2,127)+integer(3,128)+integer(4,2**63-1)+integer(5,129)+blob(6,'fixture:item/token')+integer(7,1))
assert expected==bytes.fromhex(Path('protocol/golden-claim.hex').read_text())
Path('build/ko-10').mkdir(exist_ok=True)
for kind,exe in [('cpp','build/client/n3e-peer'),('rust','target/debug/n3e-server')]:
    subprocess.run([exe,'--golden',f'build/ko-10/{kind}'],check=True)
    assert Path(f'build/ko-10/{kind}-claim.bin').read_bytes()==expected
# Rehashed engine10 releases must include durable life, and the producer refuses omission.
m=json.loads((Path('build/loot-source')/'package.json').read_text())
with tempfile.TemporaryDirectory(dir='build') as temp:
    root=Path(temp)/'source';shutil.copytree('build/loot-source',root)
    del m['life'];(root/'package.json').write_text(json.dumps(m))
    try:main.cook(root,Path(temp)/'bad')
    except ValueError:pass
    else:raise AssertionError('producer accepted loot without durable life')
    out=Path(temp)/'release';shutil.copytree(package,out);(out/'life.bin').unlink()
    files={p.name:p.read_bytes() for p in out.iterdir() if p.name not in ('release.bin','release.sha256')}
    index=b'N3R1'+u(1)+u(10)+u(5)+string(m['game_id'])+string(m['package_version'])+u(len(files))
    for name,data in sorted(files.items()):index+=string(name)+u(len(data))+digest(data)
    (out/'release.bin').write_bytes(index)
    for cmd in [['build/client/n3e-asset-check',str(out)],['target/debug/n3e-server','--check-content']]:
        result=subprocess.run(cmd,env={**os.environ,'N3E_PACKAGE':str(out)},capture_output=True)
        assert result.returncode!=0
payload=b'N3C1'+struct.pack('<QQQI',1,2,3,len('demo:item/token'))+b'demo:item/token'+struct.pack('<I',1)
assert payload==bytes.fromhex(Path('protocol/golden-claim-payload.hex').read_text())
print('PASS loot engine10/wire5 producer/readers and independent C++/Rust claim golden')
