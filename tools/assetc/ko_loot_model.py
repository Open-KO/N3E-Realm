"""Offline ordinary ground-container artwork. Binary004564f0/00458580.

Keep legacy paths and the1.5 shape scale in Moradon's package definition.
The engine consumes a static N3S1 mesh and authoritative drop positions.
"""
import json,pathlib,struct
from common import f,u
import ko_shapes as shape
import ko_tiles,ko


def cook(assets,out):
    definition=json.loads(pathlib.Path('games/moradon/loot-model.json').read_text())
    r=shape.Reader(assets.get(definition['source']));shape._name(r)
    position=[r.f32() for _ in range(3)];rotation=[r.f32() for _ in range(4)];scale=[r.f32() for _ in range(3)]
    if position!=[0,0,0] or rotation!=[0,0,0,1] or scale!=[1,1,1] or any(shape._anim_key(r) for _ in range(3)):
        raise ValueError('unsupported loot shape transform/animation')
    collision=shape._name(r);shape._name(r)
    if r.i32()!=1:raise ValueError('ordinary loot shape requires one part')
    pivot=[r.f32() for _ in range(3)];mesh_name=shape._name(r);material=shape._material(r)
    if material['render_flags'] or material['diffuse_alpha']!=1:raise ValueError('loot material unsupported')
    count=r.i32();r.f32()
    if not 1<=count<=64:raise ValueError('loot textures')
    textures=[shape._name(r)for _ in range(count)]
    if len(set(textures))!=1:raise ValueError('animated loot texture unsupported')
    if any(r.i32()for _ in range(5)) or r.at!=len(r.data):raise ValueError('loot event shape unsupported')
    assets.get(mesh_name);assets.get(collision)
    normalized=mesh_name.replace('\\','/').casefold()
    path=next(p for p in assets.root.rglob('*.n3pmesh')if p.relative_to(assets.root).as_posix().casefold()==normalized)
    mesh=ko.import_mesh(path,1.)
    width,height,rgba=ko_tiles.mip_chains(assets.get(textures[0]),skip=1)[0][0]
    if any(a!=255 for a in rgba[3::4]):raise ValueError('loot alpha unsupported')
    rgb=bytes(c for i,c in enumerate(rgba)if i%4!=3)
    # Static N3S1: one identity root/joint, no tracks; same bounded native reader.
    identity=[1 if i%5==0 else 0 for i in range(16)]
    data=b'N3S1'+u(width)+u(height)+rgb+u(1)+struct.pack('<i',-1)+f([0,0,0,0,0,0,1,1,1,1])
    data+=u(1)+u(0)+f(identity)+u(0)+u(len(mesh['vertices']))
    for v in mesh['vertices']:
        data+=f([v[0]+pivot[0],v[1]+pivot[1],v[2]-pivot[2]]+v[3:])+u(0)*4+f([1,0,0,0])
    data+=u(len(mesh['indices']))+b''.join(u(i) for i in mesh['indices'])+f([definition['scale']]*3)+u(0)
    out.write_bytes(data)
    return dict(definition=definition,vertices=len(mesh['vertices']),triangles=len(mesh['indices'])//3,sources=assets.sources.copy(),limits=['static model','visible-mesh picking','drop-position anchor; corpse-side offset/fade remain open'])
