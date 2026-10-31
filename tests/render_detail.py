"""Original fixtures for native mip chains and bounded skinned detail data."""
import copy, pathlib, struct, subprocess, sys, tempfile
sys.path.insert(0,'tools/assetc')
import ko_tiles, ko_normals, render_detail
from common import u, f

# Each authored mip has a different solid color: regenerating loses this signal.
header=struct.pack('<i4s4i',0,b'NTF\x03',16,16,25,1)
data=header+b''.join(struct.pack('<H',color)*(size*size) for size,color in [(16,0xfc00),(8,0x83e0),(4,0x801f)])
chain=ko_tiles.mip_chains(data)[0]
assert [(w,h) for w,h,_ in chain]==[(16,16),(8,8),(4,4)]
assert [p[:4] for _,_,p in chain]==[bytes([255,0,0,255]),bytes([0,255,0,255]),bytes([0,0,255,255])]
assert ko_tiles.mip_chains(data,skip=1)[0]==chain[1:]
assert ko_tiles.mip_chains(data,skip=2)[0]==chain[2:]
for bad in (data[:-1],data+b'\0'):
    try:ko_tiles.mip_chains(bad)
    except ValueError:pass
    else:raise AssertionError('truncated/trailing texture accepted')
# Upright borders, flat interior, and a sloped even-parity interior independent
# analytic plane normal. Odd-parity binary's third wedge is intentionally distinct.
n=5
flat=ko_normals.normals(dict(width=n,spacing=4,heights=[3.]*(n*n)))
assert flat==[[0.,1.,0.]]*(n*n)
plane=ko_normals.normals(dict(width=n,spacing=4,heights=[float(x*4) for z in range(n) for x in range(n)]))
for z in range(n):
    for x in range(n):
        v=plane[z*n+x]
        if x in (0,n-1) or z in (0,n-1):assert v==[0,1,0]
        elif (x+z)%2==0:assert max(abs(a-b) for a,b in zip(v,[-2**-.5,2**-.5,0]))<1e-6
assert plane[n+2]!=plane[2*n+2]
print('PASS authored native mip colors/skipping/truncation and binary terrain border/parity normals')

vertices=[([x,0,z],[0,1,0],[x,z],[0,0,0,0],[1,0,0,0],0) for x,z in [(0,0),(1,0),(0,1),(1,1)]]
geometry=(vertices[:3],[0,1,2])
attachment=(vertices,[0,1,2,0,1,2])
pm=dict(min_vertices=3,min_indices=3,controls=[(0,4),(100,3)],splits=[(3,1,1,0,0,0)],edits=[3])
args=dict(view=[1.134464,.5,256],thresholds=[[6,18,32,128]]*4,workload=[30,60,100],world_count=1,textures=[chain],radius=1,levels=[geometry]*4,attachments=[(attachment,pm)])
with tempfile.TemporaryDirectory(dir='build') as tmp:
    def check(a,good=True,payload=None):
        (pathlib.Path(tmp)/'render-detail.bin').write_bytes(render_detail.serialize(**a) if payload is None else payload)
        r=subprocess.run(['build/client/n3e-lod-check',tmp],capture_output=True,text=True)
        assert (r.returncode==0)==good,(r.returncode,r.stdout,r.stderr)
    check(args)
    changes=[lambda a:a.update(radius=0),lambda a:a.update(world_count=2),
             lambda a:a.update(levels=[geometry]*3),lambda a:a.update(workload=[30,30,100]),
             lambda a:a.update(thresholds=[[6,6,32,128]]*4),
             lambda a:a['attachments'][0][1].update(edits=[99]),
             lambda a:a['attachments'][0][1].update(min_vertices=5),
             lambda a:a['attachments'][0][1].update(splits=[(3,1,1,0,0,2)]),
             lambda a:a.update(textures=[[(16,16,chain[0][2]),(4,4,chain[2][2])]]),
             lambda a:a['levels'][0][0].__setitem__(0,([0,0,0],[0,1,0],[0,0],[1,0,0,0],[1,0,0,0],0)),
             lambda a:a['levels'][0][1].__setitem__(0,99)]
    for change in changes:
        bad=copy.deepcopy(args);change(bad);check(bad,False)
    valid=render_detail.serialize(**args)
    check(args,False,valid[:-1]);check(args,False,valid+b'\0')
print('PASS N3D1 four-level skinning, per-instance reversible attachment LOD and malformed bounds')
