"""Original static container fixture and hostile native scene loading."""
import hashlib,json,os,pathlib,shutil,struct,subprocess,sys,tempfile
sys.path.insert(0,'tools/assetc')
import main
from common import f,u
with tempfile.TemporaryDirectory(dir='build') as tmp:
    root=pathlib.Path(tmp)/'source';out=pathlib.Path(tmp)/'package';shutil.copytree('games/demo',root)
    m=json.loads((root/'package.json').read_text());m['presentation']['loot-model.bin']='loot-model.bin'
    (root/'package.json').write_text(json.dumps(m))
    data=b'N3S1'+u(1)+u(1)+bytes([255,255,255])+u(1)+struct.pack('<i',-1)+f([0,0,0,0,0,0,1,1,1,1])
    data+=u(1)+u(0)+f([int(i%5==0)for i in range(16)])+u(0)+u(3)
    for x,y in [(0,0),(1,0),(0,1)]:data+=f([x,y,0,0,0,1,x,y])+u(0)*4+f([1,0,0,0])
    data+=u(3)+u(0)+u(1)+u(2)+f([1,1,1])+u(0)
    def cook(payload):
        (root/'loot-model.bin').write_bytes(payload);main.cook(root,out)
    def client(good):
        r=subprocess.run(['build/client/n3e-asset-check',str(out)],capture_output=True,text=True)
        assert (r.returncode==0)==good,(r.stdout,r.stderr)
    cook(data);client(True)
    # New opening policy is optional. Legacy packages retain their claim-radius
    # gate; opted-in packages are validated by producer and both readers.
    m['presentation']['loot-policy.bin']='loot-policy.bin'
    (root/'package.json').write_text(json.dumps(m))
    policy=b'N3LP'+f([10])
    (root/'loot-policy.bin').write_bytes(policy);cook(data);client(True)
    r=subprocess.run(['target/debug/n3e-server','--check-content'],env={**os.environ,'N3E_PACKAGE':str(out)},capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    for bad_policy in [policy[:-1],policy+b'\0',b'N3LP'+f([0]),b'N3LP'+f([101]),b'N3LP'+f([float('nan')])]:
        (root/'loot-policy.bin').write_bytes(bad_policy)
        try:cook(data)
        except ValueError:pass
        else:raise AssertionError('bad loot policy accepted by producer')
    (root/'loot-policy.bin').write_bytes(policy);cook(data)
    original_index=(out/'release.bin').read_bytes()
    needle=struct.pack('<I',len('loot-policy.bin'))+b'loot-policy.bin'
    at=original_index.index(needle)+len(needle)
    for bad_policy in [policy[:-1],policy+b'\0',b'NOPE'+f([10]),b'N3LP'+f([-1]),b'N3LP'+f([101]),b'N3LP'+f([float('inf')])]:
        # A valid hash/index must not hide a malformed policy from either reader.
        (out/'loot-policy.bin').write_bytes(bad_policy)
        index=original_index[:at]+struct.pack('<I',len(bad_policy))+hashlib.sha256(bad_policy).digest()+original_index[at+36:]
        (out/'release.bin').write_bytes(index);(out/'release.sha256').write_text(hashlib.sha256(index).hexdigest()+'\n')
        client(False)
        r=subprocess.run(['target/debug/n3e-server','--check-content'],env={**os.environ,'N3E_PACKAGE':str(out)},capture_output=True,text=True)
        assert r.returncode!=0,'server accepted malformed rehashed loot policy'
    cook(data)
    m['presentation'].pop('loot-model.bin');(root/'package.json').write_text(json.dumps(m))
    try:main.cook(root,out)
    except ValueError:pass
    else:raise AssertionError('orphan loot policy accepted')
    m['presentation']['loot-model.bin']='loot-model.bin';(root/'package.json').write_text(json.dumps(m));cook(data)
    r=subprocess.run(['target/debug/n3e-server','--check-content'],env={**os.environ,'N3E_PACKAGE':str(out)},capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    for bad in [data[:-1],data+b'\0',data[:-16]+f([0,1,1])+u(0),data[:-16]+f([float('inf'),1,1])+u(0),data[:-16]+f([101,1,1])+u(0)]:
        cook(bad);client(False)
    cook(data);client(True)
    # Authenticated release hashes protect the file even though server geometry
    # handling is intentionally opaque, like the other presentation meshes.
    (out/'loot-model.bin').write_bytes(data[:-1])
    client(False)
    r=subprocess.run(['target/debug/n3e-server','--check-content'],env={**os.environ,'N3E_PACKAGE':str(out)},capture_output=True,text=True)
    assert r.returncode!=0
    print('PASS static loot presentation identity, native bounds/truncation/trailing rejection and C++/Rust hash tampering rejection')
