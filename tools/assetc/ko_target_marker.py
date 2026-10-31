"""Original target symbol importer; binary005c4e20,004429b0,00443090.

Only the audited static additive terrain/upright parts are accepted. Artwork
stays local, while package-owned dimensions/geometry reach the generic renderer.
"""
import hashlib,json,pathlib,struct
from common import f,u
import ko,ko_character as character,ko_shapes as shape,ko_tiles


def cook(assets,out,npc_scale=1.0):
    """`npc_scale`: the package NPC's drawn size factor (PQ-296, as PQ-288 gives
    the nameplate style). KO's symbol (005c4e20) scales by the selected actor's
    radius and height getters (0045a1d0, 00459ff0), which multiply the joint
    bounds' radius (+0x168) and height (+0x17c) by the character scale +0x90,
    the NPC-in's sSize x 0.01 (005cdd82-005cdda9, 0041f800). The NPC profile is
    the skeleton's radius and box top times that factor; the player's stays as
    measured."""
    if type(npc_scale) not in (int,float) or not 0.01<=npc_scale<=10:raise ValueError('target marker npc scale')
    definition=pathlib.Path('games/moradon/target-marker.json')
    config=json.loads(definition.read_text());profiles=[]
    for name in config['skeletons']:
        # PQ-301: the radius and the padded box top (0041c300 at frame 0), as
        # 0045a1d0 and 00459ff0 return them, not the box's Y span.
        profiles.append(list(character.joint_bounds(character.skeleton(assets.get(name)))))
    measured=[list(v) for v in profiles]
    if len(profiles)!=2:raise ValueError('target marker needs a player and an NPC skeleton')
    profiles[1]=[v*npc_scale for v in profiles[1]]
    r=shape.Reader(assets.get(config['source']));shape._name(r)
    position=[r.f32() for _ in range(3)];rotation=[r.f32() for _ in range(4)];scale=[r.f32() for _ in range(3)]
    if any(abs(v)>1e-6 for v in position) or rotation!=[0,0,0,1] or scale!=[1,1,1] or any(shape._anim_key(r) for _ in range(3)):
        raise ValueError('animated target shape unsupported')
    if shape._name(r) or shape._name(r):raise ValueError('target collision unsupported')
    count=r.i32()
    if count!=2:raise ValueError('expected two target parts')
    data=b'N3TM'+f([config['diameter_scale'],config['height_scale'],config['ground_lift']])+f(profiles[0]+profiles[1])+u(count)
    parts=[]
    for ordinal in range(count):
        pivot=[r.f32() for _ in range(3)];pivot[2]*=-1
        mesh_name=shape._name(r);material=struct.unpack('<17f6I',r.take(92))
        if material[17:]!=(4,0,2,9 if ordinal==0 else 1,2,2) or material[:4]!=(1,1,1,1):
            raise ValueError('unsupported target material')
        if r.i32()!=1:raise ValueError('animated target texture unsupported')
        r.f32();texture=shape._name(r);assets.get(mesh_name)
        normalized=mesh_name.replace('\\','/').casefold()
        path=next(p for p in assets.root.rglob('*.n3pmesh') if p.relative_to(assets.root).as_posix().casefold()==normalized)
        mesh=ko.import_mesh(path,1.)
        width,height,rgba=ko_tiles.mip_chains(assets.get(texture))[0][0]
        if not(1<=width<=512 and 1<=height<=512):raise ValueError('target texture bounds')
        if len(mesh['vertices'])!=4:raise ValueError('target quad required')
        mode=1 if ordinal==0 else 0
        data+=u(mode)+f(pivot)+u(width)+u(height)+rgba+u(len(mesh['vertices']))
        data+=b''.join(f(v) for v in mesh['vertices'])+u(len(mesh['indices']))+b''.join(u(i) for i in mesh['indices'])
        parts.append(dict(mode=mode,pivot=pivot,mesh=mesh_name,texture=texture,material=list(material),texture_size=[width,height]))
    if any(r.i32() for _ in range(5)) or r.at!=len(r.data):raise ValueError('target events/trailing bytes')
    out.write_bytes(data)
    return dict(definition=str(definition),definition_sha256=hashlib.sha256(definition.read_bytes()).hexdigest(),profiles=profiles,measured_profiles=measured,npc_scale=npc_scale,parts=parts,sources=assets.sources.copy(),limits=['static ordinary target symbol','one player and one NPC model','generated mip chain'])
