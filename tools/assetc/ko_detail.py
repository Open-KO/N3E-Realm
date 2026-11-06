"""Local KO detail data. Binary addresses and per-input hashes are in provenance."""
from common import *
import ko_character as character
import ko_tiles
import render_detail

THRESHOLDS=[[6,18,32,128],[4,12,21,85],[2.66,8,14.21,56.8],[1.77,5.33,9.48,37.9]]

def bind_world(assets,definition):
    """The player skeleton's joint matrices at frame 0, in engine space; their
    largest y is KO's Height() (ko_appearance.cook, PQ-317's plug scale)."""
    world=[]
    for b in character.skeleton(assets.get(definition['joint'])):
        p,q=character.converted(b,0,1.)
        m=character.matrix(p,q)
        if b['parent']>=0:m=character.multiply(world[b['parent']],m)
        world.append(m)
    return world


def influence_report(levels,appearances):
    """{'many_influences': ...} when a drawn corner has more than four joint
    influences (RQ-164): such corners per character level and per appearance
    key's level, and the most a corner has; {} otherwise, so a cook without
    them keeps its provenance."""
    def corners(geometry):return sum(1 for v in geometry[0] if any(w>0 for w in v[4][4:]))
    found=[corners(g) for g in levels]
    keys={key:[corners(g) for g in meshes] for key,(_,meshes) in enumerate(appearances,1) if any(corners(g) for g in meshes)}
    if not any(found) and not keys:return {}
    most=max(len(v[3]) for g in list(levels)+[g for _,ms in appearances for g in ms] for v in g[0])
    return {'many_influences':dict(levels=found,appearances=keys,most=most)}


def cook(assets_root,built,definition,mappings=(),world_root=None,positions=None):
    """Render detail (N3D1/N3D2/N3D3, or N3DI/N3DJ when a body or appearance
    part has a drawn vertex past four joint influences: RQ-164, engine 44,
    render_detail.serialize). An N3W2 build's world textures are its N3WT
    (`ko_scene.world_textures_bytes`), so its world subset is the transparent slot alone.
    `world_root` is the map's client root when it is not the character's (PQ-274).
    `positions` is the KO part position of each of the definition's parts
    (ko_player.looks), which a robe row needs (RQ-199, ko_appearance.cook)."""
    assets=character.Assets(assets_root)
    import ko_scene
    if built['atlas'] is None:textures,sources=[ko_scene.CLEAR_TEXTURE],{}
    else:textures,sources=ko_scene.world_chains(world_root or assets_root,built)
    world_count=len(textures)
    levels=[([],[]) for _ in range(4)]
    world=bind_world(assets,definition)
    spans=[max(m[a][3] for m in world)-min(m[a][3] for m in world) for a in range(3)]
    # 0041c300: joint bounds, +/-.25 padding for each extent below .5.
    radius=math.sqrt(sum((v+.5 if v<.5 else v)**2 for v in spans))*.5
    body_slots=[];rebuilt=[]
    for name in definition['parts']:
        part=character.part(assets.get(name));slot=len(textures);body_slots.append(slot)
        # 0064b9b0 default LOD_Chr=0 is incremented and clamped to one.
        textures.append(ko_tiles.mip_chains(assets.get(part['texture']),skip=1)[0])
        # RQ-164: every influence of a vertex, as KO's skinning 00419f00 sums
        # them (the Arch Tuarek's lower part has 49 with five).
        _,skins=character.skins(assets.get(part['skin']),influences=True)
        for level,skin in enumerate(skins):
            vertices,indices=levels[level];base=len(vertices)
            # RQ-187: a drawn corner whose normal has no direction takes its
            # triangle's (D-177, ko_character.corner_normals, as the player
            # scene and ko_appearance.part_levels do): the Arch Tuarek's
            # upc_ka_at_feet LOD 3 has two. KO's part draw 00412570 copies the
            # normal as loaded (00440730 -> 004401b0 / 00440440, binary).
            # Every other corner keeps its normal as read.
            normals,fixed=character.corner_normals(skin)
            if fixed:rebuilt.append(dict(part=name,level=level,vertices=len(fixed),
                                         corners=sum(1 for i in skin['indices'] if i in fixed)))
            for corner,index in enumerate(skin['indices']):
                p=skin['origins'][index];n=normals[corner]
                uv=skin['uv'][skin['uv_indices'][corner]]
                vertices.append(([p[0],p[1],-p[2]],[n[0],n[1],-n[2]],uv,
                                 skin['joints'][index],skin['weights'][index],slot))
            for i in range(0,len(skin['indices']),3):indices.extend([base+i,base+i+2,base+i+1])
    # Zone initialization 005d59f0: 65 degrees, .5 near. Moradon local table
    # factor .5 times default ViewPort Distance 512 = 256 (clear-weather factor 1).
    view=[struct.unpack('<f',struct.pack('<I',0x3f91361e))[0],.5,256.]
    import ko_appearance
    appearances,states,appearance_report,weapons=ko_appearance.cook(assets,mappings,world,textures,body_slots,positions)
    # PQ-348 (D-191): N3D3 only when a part's render state is not opaque.
    states=states if ko_appearance.needs_states(states) else None
    payload=render_detail.serialize(view,THRESHOLDS,[30,60,100],world_count,textures,radius,levels,appearances=appearances,
                                    states=states,influences=True)
    report=dict(view=view,character_radius=radius,character_triangles=[len(x[1])//3 for x in levels],
                textures=len(textures),**influence_report(levels,appearances),
                **(dict(rebuilt_normals=rebuilt) if rebuilt else {}),native_mip_levels=sum(len(c) for c in textures),
                native_pixel_bytes=sum(len(p) for c in textures for _,_,p in c),
                world_sources=sources,character_sources=assets.sources,
                texture_policy=dict(character_skip=1,shape_skip=0,terrain_skip=0),
                attachments=0,appearances=appearance_report,appearance_states='N3D3' if states else None,weapon_effects=weapons,attachment_note='equipment meshes selected by public cosmetic key' if mappings else 'unarmed default-looks character has no equipped plugs')
    return payload,report
