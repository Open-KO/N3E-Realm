"""Original exploration assets and independently rehashed hostile policy data."""
import hashlib,json,os,pathlib,shutil,struct,subprocess,sys,tempfile
sys.path.insert(0,'tools/assetc')
import main,exploration
from common import u,string
B=pathlib.Path('build/kx');B.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=B) as td:
    root=pathlib.Path(td)/'source';out=pathlib.Path(td)/'package'
    shutil.copytree('games/demo',root)
    m=json.loads((root/'package.json').read_text())
    m.update(engine_version=13,protocol_version=7,world='map.bin',exploration=dict(turbo_multiplier=10,fog_start=192,fog_end=256,fog_color=[.6,.7,.8],lod='lod.bin'))
    (root/'package.json').write_text(json.dumps(m))
    vs=[[0,0,0,0,1,0,0,0,0,0,0,0],[4,0,0,0,1,0,1,0,0,0,0,0],[0,0,4,0,1,0,0,1,0,0,0,0]]
    world=b'N3W1'+u(16)+u(16)+u(8)+u(1)+bytes([255])*16*16*4+u(3)+b''.join(struct.pack('<12f',*v) for v in vs)+u(3)+u(0)+u(1)+u(2)
    (root/'map.bin').write_bytes(world)
    lod=b'N3L2'+u(1)+struct.pack('<5f',2,0,2,4,1)+u(0)+u(1)+struct.pack('<f',0)+u(3)+u(0)+u(1)+u(2)
    (root/'lod.bin').write_bytes(lod)
    main.cook(root,out)
    def check(good,client_only=False):
        commands=[['build/client/n3e-asset-check',str(out)]]
        if not client_only:commands+=[['target/debug/n3e-server','--check-content']]
        for cmd in commands:
            r=subprocess.run(cmd,env={**os.environ,'N3E_PACKAGE':str(out)},capture_output=True,text=True)
            assert (r.returncode==0)==good,(cmd,r.stdout,r.stderr)
    check(True)
    index=(out/'release.bin').read_bytes()
    def replace(name,data):
        old=(out/name).read_bytes();(out/name).write_bytes(data)
        r=(out/'release.bin').read_bytes();needle=string(name)+u(len(old))+hashlib.sha256(old).digest()
        assert needle in r
        (out/'release.bin').write_bytes(r.replace(needle,string(name)+u(len(data))+hashlib.sha256(data).digest()))
    original=(out/'exploration.bin').read_bytes()
    for offset,value in [(4,11),(4,float('nan')),(8,300),(12,0),(16,2)]:
        data=bytearray(original);struct.pack_into('<f',data,offset,value)
        replace('exploration.bin',data);check(False);replace('exploration.bin',original)
    replace('exploration.bin',original[:-1]);check(False);replace('exploration.bin',original)
    # Legacy repeat/no-fog data remains readable. New per-part presentation bits
    # require N3L2; rehashing must not bypass version/unknown-bit validation.
    for version,flags,good in [(b'N3L1',0,True),(b'N3L1',1,True),(b'N3L2',2,True),(b'N3L2',5,True),(b'N3L2',7,True),
                               (b'N3L2',8,False),(b'N3L1',2,False),(b'N3L3',0,False)]:
        data=bytearray(lod);data[:4]=version;struct.pack_into('<I',data,28,flags)
        replace('world-lod.bin',data);check(good,True)
    replace('world-lod.bin',lod)
    bad=bytearray(lod);struct.pack_into('<I',bad,len(bad)-4,3)
    replace('world-lod.bin',bad);check(False,True)
    print('PASS exploration original fixture, both readers, rehashed multiplier/NaN/fog/color/truncation and invalid LOD index')
