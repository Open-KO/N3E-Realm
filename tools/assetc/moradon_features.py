"""Connect verified reusable capabilities to local Moradon artwork.

Service placement and most gameplay rules are original demo data. The worm
archetype, its spawn areas and the player start area come from the committed
reference extract `games/moradon/ko-reference.json` (local-asset rows whose
column meanings are binary-confirmed; see docs/implementation/evidence/ko-moradon-npc-data.md).
"""
import json,math,shutil
from pathlib import Path
import animation,ko_character,ko_npc_looks,ko_survey

REFERENCE=Path('games/moradon/ko-reference.json')
# Original demo waypoints (not KO data) from the town-square start through the
# diagonal castle-bridge exit (tests/moradon_bridges.py) to each worm area. Every
# build proves them with the engine solver and fails closed.
ROUTES=[[[58.28,-91.86],[0,-36.7]],[[58.28,-91.86],[0,-36.7],[4,-28]]]
# PQ-223 (D-171): the same demo routes on other Moradon layouts (ko_bake
# MORADON_LAYOUTS). On the classic map (Zones\moradon.*) the engine solver stops
# at once on the leg from (4, -28) to area 1, beside a transport stone placed
# there as obj_el_trans_stone4 (the default map's is obj_el_trans_stone5s), so
# its route turns at (2, -24) instead; area 0's route is unchanged.
# PQ-224 (D-172): the 1097 Moradon (the 1097 install's key 21) places the same
# obj_el_trans_stone4 at the same point as the classic map, and the solver stops
# on the same leg (at (4.10, -27.82)), so it takes the classic routes.
CLASSIC_ROUTES=[[[58.28,-91.86],[0,-36.7]],[[58.28,-91.86],[0,-36.7],[2,-24]]]
LAYOUT_ROUTES={'classic':CLASSIC_ROUTES,'1097':CLASSIC_ROUTES}
HALF=256  # centred 512 m Moradon bake: n3e (x, z) = (ko_x - 256, 256 - ko_z)


def reference():
    return json.loads(REFERENCE.read_text())


# n3e's drawn-scale bound in percent (tools/assetc/npc.py SCALE, PQ-272).
SCALE_PERCENT=(1,1000)


def drawn_scale(monster=None):
    """The worm's drawn size as a factor: its K_MONSTER sSize x 0.01 (PQ-288).

    AI Server 00437fb4 copies sSize into the template (+0x28), the spawn load
    copies it to the NPC (00438c42) and the NPC info record sends it (004221d5);
    Ebenezer relays it into the NPC-in record (00479e7c) and the client's NPC-in
    multiplies it by 0.01 into the character's scale (005cdd82-005cdda9,
    0041f800, 0043b650). The package's one NPC set is untemplated (N3N2), so the
    cook carries the factor as that set's instance scale and in the NPC name
    height (ko_nameplates), not on the wire."""
    m=reference()['monster'] if monster is None else monster
    size=m.get('sSize')
    if type(size) is not int or not SCALE_PERCENT[0]<=size<=SCALE_PERCENT[1]:
        raise ValueError(f'worm sSize {size!r} outside {SCALE_PERCENT[0]}..{SCALE_PERCENT[1]}')
    return size/100


def _area(left,top,right,bottom):
    """Inclusive KO integer rectangle as an n3e (x0, z0, x1, z1) rectangle."""
    x0,x1=sorted((left,right));z0,z1=sorted((top,bottom))
    return (x0-HALF,HALF-z1,x1-HALF,HALF-z0)


def start_area():
    s=reference()['start_position']
    # Both nations share the Moradon start; bRange widens it on each axis.
    if (s['sKarusX'],s['sKarusZ'])!=(s['sElmoradX'],s['sElmoradZ']):raise ValueError('nation start positions differ')
    return _area(s['sKarusX']-s['bRangeX'],s['sKarusZ']-s['bRangeZ'],s['sKarusX']+s['bRangeX'],s['sKarusZ']+s['bRangeZ'])


def worm(rules,progression,heightfield,faces,triangles,scratch,spawn,routes=ROUTES):
    """Apply the reference worm row and place one slot per KO spawn member."""
    ref=reference();m=ref['monster']
    # AI loader chain 0041737b -> 00437fb4 -> 0043893e: HP, attack interval (ms),
    # run speed (bySpeed x 1.5 m per 1.5 s step = m/s), search and tracing ranges.
    rules.update(npc_health=m['iHpPoint'],npc_cooldown_ticks=m['sAttackDelay']//50,npc_speed=float(m['bySpeed2']),
                 aggro_range=float(m['bySearchRange']),leash_range=float(m['byTracingRange']))
    progression['npc_level']=m['sLevel']
    spawns=[];slots=[];report=[]
    if len(routes)!=len(ref['spawns']):raise ValueError('one demo route per reference spawn row')
    movement=dict(rules['movement'],speed=rules['speed'])
    for row,waypoints in zip(ref['spawns'],routes):
        if row['NpcID']!=m['sSid']:raise ValueError('reference spawn/template mismatch')
        area=_area(row['LeftX'],row['TopZ'],row['RightX'],row['BottomZ'])
        found=ko_survey.area_candidates(triangles,area)
        origin=None
        for c in found[:24]:
            if ko_survey.verify(triangles,c['position'],scratch)['open']:origin=c['position'];break
        if origin is None:raise ValueError('reference spawn area has no engine-verified point')
        ox,oz=int(round(origin[0])),int(round(origin[2]))
        if (ox,oz)!=(origin[0],origin[2]):raise ValueError('slot point is not an integer point')
        # AI 0041b89c: respawn = RegTime seconds, raised to 30 when below 15.
        seconds=row['RegTime'] if row['RegTime']>=15 else 30
        for _ in range(row['NumNPC']):
            spawns.append([float(ox),float(oz)])
            slots.append({'area':[area[0]-ox,area[1]-oz,area[2]-ox,area[3]-oz],'respawn_ticks':seconds*20})
        path=[list(w) for w in waypoints]+[[ox,oz]]
        reached,end,missed=ko_survey.route(triangles,spawn,path,movement,scratch)
        if not reached:raise ValueError(f'demo route to worm area {list(area)} blocked near {missed} at {end}')
        report.append({'area':list(area),'point':[ox,oz],'members':row['NumNPC'],'respawn_seconds':seconds,'route':path})
    # ActType 1-4 is passive (AI 0042476d); 10 s give-up renewed by hits (00425546,
    # 0041f715); home walk at twice run speed without healing (0042890f); stand
    # time as recovery; maxHP/20 every 10 s (004248e5); 500 spawn tries (00419489).
    passive=1<=m['byActType']<=4
    npc={'model':'reference_melee_v2','scan_ticks':10,'acquire_ticks':10,'stuck_ticks':40,
         'chase_ticks':200,'return_ticks':200,'recovery_ticks':m['sStandtime']//50,
         'acquisition':'passive' if passive else 'aggressive','renew_on_hit':True,'return_heal':False,
         'retaliate_returning':True,'return_speed_percent':200,'regen_interval_ticks':200,'regen_divisor':20,
         'spawn_tries':500,'slots':slots}
    return spawns,npc,report


def apply(root,manifest,assets,spawn,heightfield,faces,player,layout=None):
    import main
    definition=json.loads(Path('games/moradon/features.json').read_text())
    manifest.update(definition)
    manifest.update(engine_version=33,protocol_version=26,package_version='0.6.0')
    rules=manifest['gameplay']
    # The synthetic 25 m starter spell range still exceeds the 3 m reference search range;
    # passive worms are acquired by damage, and the 40 m tracing range bounds pursuit.
    rules.update(health=300,npc='demo:creature/worm',spawn_x=spawn[0],spawn_z=spawn[2])
    # Use the actual engine's collision walk to select reachable original service
    # and combat points from the surveyed player spawn. No guessed map heights.
    triangles=ko_survey._surface(heightfield)+[p for tri in faces for p in tri]
    scratch=root/'feature-route.txt';routes=[]
    for dx,dz in [(1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,1),(1,-1),(-1,-1)]:
        length=math.hypot(dx,dz);direction=(dx/length,dz/length)
        points=ko_survey._walk('build/client/n3e-walk-check',triangles,spawn,[direction]*160,scratch)
        end=points[-1]
        distance=math.hypot(end[0]-spawn[0],end[2]-spawn[2])
        if distance>=7:routes.append((distance,points))
    if not routes:raise ValueError('Moradon has no verified nearby combat route')
    routes.sort(key=lambda r:r[0],reverse=True)
    combat=[]
    for _,points in routes:
        end=points[-1]
        if all(math.hypot(end[0]-p[0],end[2]-p[2])>4 for p in combat):combat.append(end)
        if len(combat)==3:break
    worm_routes=ROUTES if layout is None else LAYOUT_ROUTES[layout]
    worm_spawns,worm_npc,worm_report=worm(rules,manifest['progression'],heightfield,faces,triangles,scratch,spawn,worm_routes)
    rules['spawns']=worm_spawns
    manifest['npc']=worm_npc
    # Two distinct service labels beside the safe spawn, both within use radius.
    manifest['commerce']['shops'][0]['position']=[float(v)for v in spawn]
    manifest['storage']['services'][0]['position']=[float(v)for v in routes[0][1][15]]
    clips=[ko_character.animation_metadata(player[state]) for state in animation.STATES]
    for state in animation.REST_STATES:
        clips.append(ko_character.animation_metadata(player[state]))
        name=f'player-{state}.bin'
        shutil.copyfile(root/'player'/name,root/name)
        manifest['presentation'][name]=name
    manifest['rest']=dict(interval_ticks=101,sit_cooldown_ticks=60,
        levels=[[int(level*(1+level/30.0))+3,5,level+29,3] for level in range(1,256)])
    config=json.loads(Path('games/moradon/combat-animation.json').read_text())
    indexes=sorted({i for p in config['profiles']for i in [p['ready'],p['moving'],*p['attacks']]})
    attacks={i for p in config['profiles']for i in [p['moving'],*p['attacks']]}
    combat_clips=[]
    for index in indexes:
        name=f'player-combat-{index}.bin';shutil.copyfile(root/'player'/name,root/name)
        clip=ko_character.animation_metadata(player[f'combat-{index}'])
        if index in attacks:clip['loop_blend']=False
        combat_clips.append(dict(source=name,**clip))
    manifest['combat_animation']=dict(clips=combat_clips,
        profiles=[dict(ready=indexes.index(p['ready']),attacks=[indexes.index(i)for i in p['attacks']],moving=indexes.index(p['moving']),interval_ms=p['interval_ms'])for p in config['profiles']],
        slots=config['slots'],rows=config['rows'],upper_nodes=config['upper_nodes'])
    reports={}
    # The worm's model is its looks row (K_MONSTER sPid, the NPC-in resource ID),
    # built and clipped as the client builds it (ko_npc_looks, PQ-254).
    source=ko_character.Assets(assets)
    row=ko_npc_looks.table(source.get(ko_npc_looks.SOURCE)).get(reference()['monster']['sPid'])
    if row is None:raise ValueError('the worm has no NPC_Looks row')
    spec,_=ko_npc_looks.definition(row,source)
    # PQ-288: the four clips are drawn at the worm's sSize (KO's character
    # matrix carries it on its diagonal, 0043b650), so each clip scene's
    # instance scale is that factor; the package's instanced scene (the
    # editable decoration) keeps 1.
    scale=drawn_scale()
    for state,index in ko_npc_looks.CLIPS:
        target=root/'npc'/state
        report=ko_character.convert(assets,ko_npc_looks.SOURCE,target,index,1.0,definition=spec,player=False)
        clip_meta=json.loads((target/'scene.json').read_text());clip_meta['instance_scale']=[scale]*3
        (target/'scene.json').write_text(json.dumps(clip_meta))
        main.cook(target,target/'cooked')
        shutil.copyfile(target/'cooked/scene.bin',root/f'npc-{state}.bin')
        clips.append(ko_character.animation_metadata(report));reports[state]=report
        manifest['presentation'][f'npc-{state}.bin']=f'npc-{state}.bin'
    for index in (2,3,7,9,12,13):clips[index]['loop_blend']=False
    manifest['animation']=clips
    for name in ('character.gltf','character.bin','atlas.png'):shutil.copyfile(root/'npc/idle'/name,root/name)
    manifest['assets'][0]['source']='character.gltf'
    meta=json.loads((root/'scene.json').read_text());meta['attachment_node']=0;meta['instance_scale']=[1,1,1]
    (root/'scene.json').write_text(json.dumps(meta))
    report={'definition':'games/moradon/features.json','origin':'original synthetic gameplay and placement',
            'spawn':spawn,'combat':combat,'worm':worm_report,'services':{'shop':manifest['commerce']['shops'][0]['position'],
            'warehouse':manifest['storage']['services'][0]['position']},'npc':reports,
            'npc_drawn_scale':{'sSize':reference()['monster']['sSize'],'instance_scale':scale},
            'limits':['one worm archetype from reference rows; damage, XP and drops remain synthetic','ordinary weapon, shield and torso appearances; trails/special effects remain open',
                      'existing native feature panels; complete original dialogs remain open',
                      'original direct/group drop rows; historical ITEM_GROUP data remains unavailable']}
    if layout is not None:report['layout']=layout  # the default report stays as pinned
    return report
