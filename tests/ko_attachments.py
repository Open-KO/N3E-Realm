"""Attachment transform audit against independently composed legacy row matrices.

Default uses original synthetic bytes. --local checks the optional Moradon inputs;
raw geometry stays local. Binary order: 004133c0 / 004137d0 / 00467b30.
"""
import json,math,pathlib,struct,sys,tempfile
sys.path.insert(0,str(pathlib.Path('tools/assetc').resolve()))
import ko_character as c,ko_appearance as a
from common import string,f,u

def row_matrix(p,q):
    x,y,z,w=q
    return [[1-2*y*y-2*z*z,2*x*y+2*z*w,2*x*z-2*y*w,0],
            [2*x*y-2*z*w,1-2*x*x-2*z*z,2*y*z+2*x*w,0],
            [2*x*z+2*y*w,2*y*z-2*x*w,1-2*x*x-2*y*y,0],list(p)+[1]]
def row_point(p,m):return [sum((p+[1])[j]*m[j][i]for j in range(4))for i in range(3)]
def world_at(bones,frame,legacy=False):
    out=[]
    for b in bones:
        if legacy:
            m=row_matrix(c.sample(b['keys'][0],frame,b['translation']),c.sample(b['keys'][1],frame,b['rotation']))
            if b['parent']>=0:m=c.multiply(m,out[b['parent']])
        else:
            m=c.matrix(*c.converted(b,frame,1))
            if b['parent']>=0:m=c.multiply(out[b['parent']],m)
        out.append(m)
    return out

def audit(assets,name,joint,bones,frames):
    r=c.Reader(assets.get(name));r.string();r.integer();r.integer()
    pos,rot,scale=r.floats(3),r.floats(16),r.floats(3)
    r.floats(17);r.unpack('6I');mesh=r.string();r.string()
    mr=c.Reader(assets.get(mesh));mr.string();_,_,nv,_,_,_=mr.unpack('6i');raw=[mr.floats(8)[:3]for _ in range(nv)]
    bind=world_at(bones,0);height=max(m[1][3]for m in bind)
    levels,_,_=a.plug_levels(assets,name,joint,bind[joint],height,0)
    factor=height/1.8*scale[1]
    plug=[[rot[j*4+i]*factor if j<3 else (pos[i]*factor if i<3 else 1)for i in range(4)]for j in range(4)]
    worst=0
    for frame in frames:
        # Expected: source vertex * plug * current legacy joint, reflected once.
        legacy=c.multiply(plug,world_at(bones,frame,True)[joint])
        palette=c.multiply(world_at(bones,frame)[joint],c.inverse(bind[joint]))
        for p,v in zip(raw,levels[0][0]):
            expected=row_point(p,legacy);expected[2]*=-1
            actual=[sum(palette[i][j]*v[0][j]for j in range(3))+palette[i][3]for i in range(3)]
            worst=max(worst,max(abs(x-y)for x,y in zip(expected,actual)))
    assert worst<2e-5,(name,joint,worst)
    return worst

if '--local' in sys.argv:
    assets=c.Assets(pathlib.Path('assets/ko'))
    bones=c.skeleton(assets.get('Chr/upc_ka_tu.n3joint'))
    clips=c.animations(assets.get('Chr/upc_ka_tu.n3anim'))
    frames=[a['start']+(a['end']-a['start'])*t for i in [0,1,2,11,12,13,86,87] for a in [clips[i]]for t in [0,.5,1]]
    errors=[]
    for row in json.loads(pathlib.Path('games/moradon/appearance.json').read_text()):
        # PQ-320: the glow package's own artwork for a row (glow_2233_source) too.
        for source in [row['source']]+([row['glow_2233_source']] if 'glow_2233_source' in row else []):
            if 'joint' in row:errors.append(dict(source=source,joint=row['joint'],max_error=audit(assets,source,row['joint'],bones,frames)))
    out=pathlib.Path('build/ko-completion/rest-items/attachment-audit.json')
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(dict(frames=frames,results=errors,hashes=assets.sources),indent=2))
    print('PASS local blade/right+left, shield, twohand and the glow package\'s Durandal: 24 animation samples, binary row-matrix order agrees within 0.00002 metres')
else:
    with tempfile.TemporaryDirectory() as td:
        root=pathlib.Path(td)
        material=f([1]*4+[0]*13)+u(0)*6
        rot=row_matrix([0,0,0],[0,0,math.sin(.4),math.cos(.4)])
        (root/'plug.bin').write_bytes(string('original')+u(0)+u(0)+f([.2,.3,.4])+f([v for row in rot for v in row])+f([1,1,1])+material+string('mesh.n3pmesh')+string('tex.bin'))
        vertices=[[1,0,0,0,0,1,0,0],[0,2,0,0,0,1,1,0],[0,0,3,0,0,1,0,1]]
        (root/'mesh.n3pmesh').write_bytes(string('original')+struct.pack('<6i',0,0,3,3,3,3)+f([v for row in vertices for v in row])+struct.pack('<3H',0,1,2)+u(0))
        (root/'tex.bin').write_bytes(string('original')+b'NTF\x03'+struct.pack('<4i',4,4,0x31545844,1)+struct.pack('<HHI',0xf800,0x07e0,0))
        bones=[dict(translation=[.7,1.8,-.2],rotation=[0,0,0,1],parent=-1,keys=[None,dict(rate=30,kind=1,values=[[0,0,0,1],[0,math.sin(.6),0,math.cos(.6)]]),None])]
        audit(c.Assets(root),'plug.bin',0,bones,[0,.5,1])
    print('PASS asymmetric plug with noncommuting rotations, scaled offset, Z reflection and animated rigid joint')
