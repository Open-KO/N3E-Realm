"""Original appearance package and independently rehashed hostile public mappings."""
import copy,json,os,shutil,struct,subprocess,sys,tempfile
from pathlib import Path
from item_drops_live import prepare
sys.path.insert(0,'tools/assetc')
import main,appearance,render_detail
from common import u,string,digest
base=prepare(full=True)
with tempfile.TemporaryDirectory(dir='build') as tmp:
    root=Path(tmp)/'source';out=Path(tmp)/'package';shutil.copytree(base.parent/'source',root)
    m=json.loads((root/'package.json').read_text());gear=m['equipment']['items'][0]
    m.update(engine_version=29,protocol_version=22,world='map.bin',render_detail='detail.bin',
        exploration=dict(turbo_multiplier=10,fog_start=192,fog_end=256,fog_color=[.6,.7,.8],lod='lod.bin'),
        appearance=[dict(item=gear['id'],slot=gear['slots'][0])])
    vs=[[0,0,0,0,1,0,0,0,0,0,0,0],[4,0,0,0,1,0,1,0,0,0,0,0],[0,0,4,0,1,0,0,1,0,0,0,0]]
    (root/'map.bin').write_bytes(b'N3W1'+u(16)+u(16)+u(8)+u(1)+bytes([255])*1024+u(3)+b''.join(struct.pack('<12f',*v) for v in vs)+u(3)+u(0)+u(1)+u(2))
    (root/'lod.bin').write_bytes(b'N3L2'+u(1)+struct.pack('<5f',2,0,2,4,1)+u(0)+u(1)+struct.pack('<f',0)+u(3)+u(0)+u(1)+u(2))
    def geometry(slot):return ([([x,0,z],[0,1,0],[x,z],[0]*4,[1,0,0,0],slot) for x,z in [(0,0),(1,0),(0,1)]],[0,1,2])
    args=dict(view=[1.134464,.5,256],thresholds=[[6,18,32,128]]*4,workload=[30,60,100],world_count=1,
        textures=[[(16,16,bytes([255])*1024)]]*3,radius=1,levels=[geometry(1)]*4,appearances=[([1],[geometry(2)]*4)])
    (root/'detail.bin').write_bytes(render_detail.serialize(**args));(root/'package.json').write_text(json.dumps(m));main.cook(root,out)
    def check(good=True,client_only=False):
        commands=[['build/client/n3e-asset-check',str(out)]]
        if not client_only:commands.append(['target/debug/n3e-server','--check-content'])
        results=[subprocess.run(c,env={**os.environ,'N3E_PACKAGE':str(out)},capture_output=True,text=True)for c in commands]
        for r in results:assert (r.returncode==0)==good,(r.stdout,r.stderr)
        if good:assert results[1].stdout.splitlines()[0] in results[0].stdout.splitlines()
    check()
    for rows in [[],m['appearance']*2,[dict(item='missing',slot=0)],[dict(item=gear['id'],slot=99)]]:
        try:appearance.cook(rows,m['equipment'])
        except ValueError:pass
        else:raise AssertionError('invalid appearance accepted')
    files={p.name:p.read_bytes()for p in out.iterdir()if p.name not in ('release.bin','release.sha256')}
    def repack(changes,remove=()):
        changed={**files,**changes}
        for name in remove:del changed[name]
        index=b'N3R1'+u(1)+u(m['engine_version'])+u(m['protocol_version'])+string(m['game_id'])+string(m['package_version'])+u(len(changed))
        for name,data in sorted(changed.items()):(out/name).write_bytes(data);index+=string(name)+u(len(data))+digest(data)
        (out/'release.bin').write_bytes(index)
    original=files['appearance.bin']
    for data in [original[:-1],original+b'\0',b'N3V1'+u(0),original[:-4]+u(99),b'N3V1'+u(2)+original[8:]*2]:
        repack({'appearance.bin':data});check(False)
    for name in ['appearance.bin','equipment.bin','render-detail.bin']:
        repack({},[name]);check(False)
    for bad in [files['render-detail.bin'][:-1],files['render-detail.bin']+b'\0']:
        repack({'render-detail.bin':bad});check(False,True)
    # PQ-348 (D-191): N3D3 is N3D2 with a render state after each appearance
    # entry (flags, alpha reference, source, destination); both readers take it
    # at the same engine, the client checks the states as N3SM runs.
    n3d2=(root/'detail.bin').read_bytes()
    state=(3,0.0,4,5)  # blend src_alpha/one_minus_src_alpha, double-sided, lit, reference 0
    n3d3=render_detail.serialize(**args,states=[state])
    assert n3d3[:4]==b'N3D3' and n3d3[4:]==n3d2[4:]+u(3)+struct.pack('<f',0)+u(4)+u(5),'N3D3 is N3D2 plus the states'
    assert render_detail.serialize(**args)==n3d2,'no states keeps the N3D2 bytes'
    for bad in [(8,0.,0,0),(4,0.,0,0),(7,0.,4,5),(1,1.,4,5),(1,float('nan'),4,5),(1,.99999999,4,5),(1,0.,10,5),(0,0.,4,5),(2,-.1,0,0),[3,0.,4,5]]:
        try:render_detail.serialize(**args,states=[bad])
        except ValueError:pass
        else:raise AssertionError(('cooked a bad state',bad))
    for bad in [[],[state]*2]:
        try:render_detail.serialize(**args,states=bad)
        except ValueError:pass
        else:raise AssertionError(('cooked a state count',len(bad)))
    (root/'detail.bin').write_bytes(n3d3);main.cook(root,out);check()
    files={p.name:p.read_bytes()for p in out.iterdir()if p.name not in ('release.bin','release.sha256')}
    good=files['render-detail.bin'];at=len(good)-16
    def forged(flags,reference,source,destination):return good[:at]+u(flags)+struct.pack('<f',reference)+u(source)+u(destination)
    for bad in [forged(8,0,0,0),forged(4,0,0,0),forged(7,0,4,5),forged(5,1.0,4,5),forged(5,float('nan'),4,5),forged(5,-.5,4,5),forged(1,0,10,5),forged(1,0,4,10),
                forged(2,0,4,5),good[:-1],good+b'\0',b'N3D1'+good[4:],b'N3D4'+good[4:]]:
        repack({'render-detail.bin':bad});check(False,True)
    repack({'render-detail.bin':b'N3D2'+good[4:]});check(False,True)  # states after an N3D2 header: trailing bytes
    repack({'render-detail.bin':b'N3D9'+good[4:]});check(False)  # the server refuses an unknown magic too
    (root/'detail.bin').write_bytes(n3d2);main.cook(root,out);check()
    files={p.name:p.read_bytes()for p in out.iterdir()if p.name not in ('release.bin','release.sha256')}
    print('PASS N3D3 appearance render states: both readers accept them at engine 29, N3D2 bytes unchanged without '
          'states, the cook and the client refuse out-of-bounds flags, references, factors and lengths')
    # Engine30 adds a complete sit/idle/stand set and bounded recovery policy.
    import rest
    m.update(engine_version=30,protocol_version=23,rest=dict(interval_ticks=101,sit_cooldown_ticks=60,levels=[[4,5,30,3]]))
    idle=m['animation'][0]
    transitions=[{**idle,'loop_blend':False},idle,{**idle,'loop_blend':False}]
    m['animation']=m['animation'][:7]+transitions+m['animation'][7:]
    for state in ['sit-down','sit-idle','stand-up']:m['presentation'][f'player-{state}.bin']=m['presentation']['player-idle.bin']
    (root/'package.json').write_text(json.dumps(m));main.cook(root,out);check()
    for bad in [dict(m['rest'],interval_ticks=0),dict(m['rest'],levels=[[4,5,0,3]]),dict(m['rest'],levels=[]),dict(m['rest'],sit_cooldown_ticks=1201)]:
        try:rest.cook(bad)
        except ValueError:pass
        else:raise AssertionError('invalid rest policy')
    files={p.name:p.read_bytes()for p in out.iterdir()if p.name not in ('release.bin','release.sha256')}
    original=files['rest.bin']
    for bad in [original[:-1],original+b'\0',original[:4]+u(0)+original[8:],original[:12]+u(256)+original[16:],original[:24]+u(0)+original[28:]]:
        repack({'rest.bin':bad});check(False)
    for name in ['rest.bin','player-sit-down.bin','player-sit-idle.bin','player-stand-up.bin']:
        repack({},[name]);check(False)
    for name in ['player-sit-down.bin','player-sit-idle.bin','player-stand-up.bin']:
        repack({name:b'BAD!'+files[name][4:]});check(False,True)
    repack({'animation.bin':files['animation.bin'][:4]+u(11)+files['animation.bin'][8:]});check(False)
    repack({},['animation.bin','player-sit-down.bin','player-sit-idle.bin','player-stand-up.bin','npc-idle.bin','npc-walk.bin','npc-attack.bin','npc-death.bin']);check(False)
    print('PASS N3E1/N3A3 rest policy, complete clips and cross-language content identity')
    # Profiles are cosmetic; their equipment selectors are validated by both readers.
    import combat_animation
    m.update(engine_version=31,protocol_version=24)
    m['combat_animation']=dict(clips=[dict(source=m['presentation']['player-idle.bin'],**idle) for _ in range(3)],
        profiles=[dict(ready=0,attacks=[1,2]),dict(ready=0,attacks=[1,2])],slots=[gear['slots'][0]],
        rows=[dict(items=[None],profile=1),dict(items=[gear['id']],profile=2)])
    for clip in m['combat_animation']['clips']:clip['loop_blend']=False
    (root/'package.json').write_text(json.dumps(m));main.cook(root,out);check()
    recipe=json.loads((out/'recipe.json').read_text())
    assert recipe['sources']['detail.bin']==digest((root/'detail.bin').read_bytes()).hex()
    config=m['combat_animation']
    for field,value in [('profiles',[dict(ready=99,attacks=[1])]),('slots',[99]),('rows',config['rows']*2),('clips',[])]:
        try:combat_animation.cook(dict(config,**{field:value}),m['inventory'],m['equipment'])
        except ValueError:pass
        else:raise AssertionError('invalid combat animation producer')
    files={p.name:p.read_bytes()for p in out.iterdir()if p.name not in ('release.bin','release.sha256')}
    original=files['combat-animation.bin']
    for off,val in [(4,0),(4,65),(8,0),(36,1),(72,99),(80,3),(84,1)]:
        bad=bytearray(original);struct.pack_into('<I',bad,off,val);repack({'combat-animation.bin':bad});check(False)
    for bad in [original[:-1],original+b'\0']:
        repack({'combat-animation.bin':bad});check(False)
    for name in ['combat-animation.bin','combat-0.bin','combat-1.bin','combat-2.bin']:
        repack({},[name]);check(False)
    for name in ['combat-0.bin','combat-1.bin','combat-2.bin']:
        repack({name:b'BAD!'+files[name][4:]});check(False,True)
    print('PASS N3A4 profiles/complete clips, equipment selectors, one-shot attacks and hostile reader bounds')

    m.update(engine_version=32,protocol_version=25)
    config['upper_nodes']=[1]
    for profile in config['profiles']:profile.update(interval_ms=1140,moving=2)
    (root/'package.json').write_text(json.dumps(m));main.cook(root,out);check()
    files={p.name:p.read_bytes()for p in out.iterdir()if p.name not in ('release.bin','release.sha256')}
    original=files['combat-animation.bin']
    for bad in [original[:-1],original+b'\0',original[:-4]+u(0),original[:-4]+u(64),original[:-8]+u(2)+u(1)+u(1),original[:88]+u(0)+original[92:]]:
        repack({'combat-animation.bin':bad});check(False)
    repack({'combat-animation.bin':original[:-4]+u(63)});check(False,True)
    print('PASS N3A5 timed profiles, moving clips, joint-mask bounds and cross-language identity')
    # PQ-416 (D-216): ranged basic attacks on N3A5 profiles, added to the
    # melee radii; both readers take and bound the same file. PQ-420 (D-217):
    # the cook writes N3RC (a cast time per entry, 0 here); N3RB still reads.
    import ranged_attack
    assert 'melee' in m,'the fixture carries the melee radii'
    good=dict(profiles=[dict(profile=2,reach=6,range=8)],notice='Skill Failed - Too far')
    m['ranged_attack']=good;(root/'package.json').write_text(json.dumps(m));main.cook(root,out);check()
    files={p.name:p.read_bytes()for p in out.iterdir()if p.name not in ('release.bin','release.sha256')}
    original=files['ranged-attack.bin']
    assert original==b'N3RC'+u(1)+u(2)+struct.pack('<2f',6,8)+u(0)+u(22)+b'Skill Failed - Too far',original
    entry=lambda **k:dict(good,profiles=[dict(good['profiles'][0],**k)])
    for bad,combat,melee in [(entry(profile=3),config,m['melee']),(entry(profile=0),config,m['melee']),(entry(reach=8.5),config,m['melee']),
                             (entry(range=.4,reach=0),config,m['melee']),(entry(range=100.5),config,m['melee']),(entry(reach=-1),config,m['melee']),
                             (entry(range=float('nan')),config,m['melee']),(entry(profile=True),config,m['melee']),
                             (dict(good,profiles=good['profiles']*2),config,m['melee']),(dict(good,profiles=[]),config,m['melee']),
                             (dict(good,notice='x'*97),config,m['melee']),(dict(good,notice='tab\there'),config,m['melee']),
                             (dict(good,notice='caf\u00e9'),config,m['melee']),(dict(good,extra=1),config,m['melee']),
                             (good,config,None),(good,{k:v for k,v in config.items() if k!='upper_nodes'},m['melee']),
                             (entry(cast_ms=900),config,m['melee']),(entry(cast_ms=True),config,m['melee']),(entry(cast_ms=1.5),config,m['melee'])]:
        try:ranged_attack.cook(bad,combat,melee)
        except ValueError:pass
        else:raise AssertionError(('cooked a bad ranged attack',bad))
    for bad in [original[:-1],original+b'\0',b'N3RA'+original[4:],original[:4]+u(0)+original[8:],original[:4]+u(33)+original[8:],
                original[:8]+u(0)+original[12:],original[:8]+u(3)+original[12:],original[:12]+struct.pack('<f',8.5)+original[16:],
                original[:12]+struct.pack('<f',-1)+original[16:],original[:16]+struct.pack('<f',.4)+original[20:],
                original[:16]+struct.pack('<f',100.5)+original[20:],original[:16]+struct.pack('<f',float('nan'))+original[20:],
                original[:24]+u(97)+original[28:]+b'x'*75,original[:24]+u(22)+b'Skill Failed\t- Too far'[:22],
                original[:4]+u(2)+original[8:24]+original[8:24]+original[24:],
                # A cast time on profile 2, whose two attack clips are profile 1's too.
                original[:20]+u(900)+original[24:],original[:20]+u(100)+original[24:],original[:20]+u(10001)+original[24:],
                b'N3RB'+original[4:]]:  # an N3RB file has no cast time: 4 bytes too many
        repack({'ranged-attack.bin':bad});check(False)
    repack({'ranged-attack.bin':original[:24]+u(0)});check()
    repack({'ranged-attack.bin':b'N3RB'+original[4:20]+original[24:]});check()  # PQ-416's layout still reads
    # A cast: profile 2 takes its own attack clip (clip 3, 1 s, blend 0.2 s,
    # first marker 0.8 s); 900 ms lands at 0.2 + 0.8 x 0.9 = 0.92 s, 19 ticks,
    # inside the 1140 ms (23-tick) interval.
    saved=json.loads(json.dumps(config))
    config['clips'].append(dict(config['clips'][1],markers=[.8,-1]))
    config['profiles'][1].update(attacks=[3],moving=3)
    assert ranged_attack.cast_landing(config,2,900)==19 and ranged_attack.cast_landing(config,2,1160)==23
    m['ranged_attack']=entry(cast_ms=900)
    (root/'package.json').write_text(json.dumps(m));main.cook(root,out);check()
    files={p.name:p.read_bytes()for p in out.iterdir()if p.name not in ('release.bin','release.sha256')}
    cast=files['ranged-attack.bin'];assert cast[20:24]==u(900),cast
    for bad,why in [(entry(cast_ms=1210),'lands at 24 ticks, after the interval'),(dict(good,profiles=[dict(profile=1,reach=6,range=8,cast_ms=900)]),'two attack clips')]:
        try:ranged_attack.cook(bad,config,m['melee'])
        except ValueError:pass
        else:raise AssertionError(('cooked a bad ranged cast',why))
    for bad in [cast[:20]+u(1210)+cast[24:],cast[:8]+u(1)+cast[12:]]:
        repack({'ranged-attack.bin':bad});check(False)
    noted=dict(config,clips=[*config['clips'][:3],dict(config['clips'][3],markers=[-1,.8])])
    try:ranged_attack.cook(entry(cast_ms=900),noted,m['melee'])
    except ValueError:pass
    else:raise AssertionError('cooked a ranged cast whose clip has no first marker')
    config.clear();config.update(saved)
    # PQ-421 (D-218): N3RD adds an ammo item (a 1-based inventory index that
    # does not wear) and count per entry, then the ammo notice; the server
    # removes the ammo in the strike's wear commit, so the package needs wear.
    assert 'wear' in m,'the fixture carries the wear policy'
    items=m['inventory']['items']
    arrow=next(i for i in items if i['durability']==0 and i['stack_limit']>1)
    worn=next(i for i in items if i['durability']>0)
    index=items.index(arrow)+1
    short='Skill Failed - Not enough item'
    def ammo(**k):return dict(entry(ammo=dict(dict(item=arrow['id'],count=1),**k)),ammo_notice=short)
    m['ranged_attack']=ammo()
    (root/'package.json').write_text(json.dumps(m));main.cook(root,out);check()
    files={p.name:p.read_bytes()for p in out.iterdir()if p.name not in ('release.bin','release.sha256')}
    rd=files['ranged-attack.bin']
    assert rd==b'N3RD'+u(1)+u(2)+struct.pack('<2f',6,8)+u(0)+u(index)+u(1)+u(22)+b'Skill Failed - Too far'+u(len(short))+short.encode(),rd
    for bad,inventory,wear in [(ammo(item='demo:item/none'),m['inventory'],m['wear']),(ammo(item=worn['id']),m['inventory'],m['wear']),
                               (ammo(count=0),m['inventory'],m['wear']),(ammo(count=arrow['stack_limit']+1),m['inventory'],m['wear']),
                               (ammo(count=True),m['inventory'],m['wear']),(ammo(extra=1),m['inventory'],m['wear']),
                               (dict(ammo(),ammo_notice='x'*97),m['inventory'],m['wear']),(dict(ammo(),ammo_notice='tab\there'),m['inventory'],m['wear']),
                               (ammo(),m['inventory'],None),(ammo(),None,m['wear'])]:
        try:ranged_attack.cook(bad,config,m['melee'],inventory,wear)
        except ValueError:pass
        else:raise AssertionError(('cooked a bad ranged ammo',bad))
    tail=rd[32:]
    for bad in [rd[:-1],rd+b'\0',rd[:24]+u(0)+u(1)+tail,rd[:24]+u(len(items)+1)+u(1)+tail,rd[:24]+u(items.index(worn)+1)+u(1)+tail,
                rd[:24]+u(index)+u(0)+tail,rd[:24]+u(index)+u(arrow['stack_limit']+1)+tail,
                rd[:58],rd[:58]+u(97)+b'x'*97,rd[:58]+u(3)+b'a\tb',b'N3RC'+rd[4:]]:
        repack({'ranged-attack.bin':bad});check(False)
    repack({'ranged-attack.bin':rd[:24]+u(0)+u(0)+tail});check()       # no ammo on the entry
    repack({'ranged-attack.bin':rd[:24]+u(index)+u(arrow['stack_limit'])+rd[32:58]+u(0)});check()  # a full stack, no ammo notice text
    # PQ-422 (D-219): N3RE adds per entry, after the ammo count, a hit kind
    # (0: the basic attack's damage, 1: a type-2 skill hit) and its hit rate
    # (1-1000), add damage (0-300) and add damage plus (0-10000), all 0 for
    # kind 0; only the server uses them, both readers bound them.
    archery=dict(hit_rate=100,add_damage=100,add_damage_plus=0)
    def skill(**k):return dict(entry(skill_hit=dict(archery,**k)),notice=good['notice'])
    m['ranged_attack']=skill()
    (root/'package.json').write_text(json.dumps(m));main.cook(root,out);check()
    files={p.name:p.read_bytes()for p in out.iterdir()if p.name not in ('release.bin','release.sha256')}
    re_=files['ranged-attack.bin']
    assert re_==b'N3RE'+u(1)+u(2)+struct.pack('<2f',6,8)+u(0)+u(0)+u(0)+u(1)+u(100)+u(100)+u(0)+u(22)+b'Skill Failed - Too far'+u(0),re_
    m['ranged_attack']=dict(ammo(),profiles=[dict(ammo()['profiles'][0],skill_hit=dict(archery,add_damage_plus=7))])
    (root/'package.json').write_text(json.dumps(m));main.cook(root,out);check()
    for bad in [skill(hit_rate=0),skill(hit_rate=1001),skill(add_damage=301),skill(add_damage=-1),skill(add_damage_plus=10001),
                skill(hit_rate=True),skill(extra=1),entry(skill_hit=dict(hit_rate=100,add_damage=100)),entry(skill_hit=[100,100,0])]:
        try:ranged_attack.cook(bad,config,m['melee'],m['inventory'],m['wear'])
        except ValueError:pass
        else:raise AssertionError(('cooked a bad ranged skill hit',bad))
    for bad in [re_[:-1],re_+b'\0',re_[:32]+u(2)+re_[36:],re_[:32]+u(0)+re_[36:],re_[:32]+u(1)+u(0)+re_[40:],
                re_[:32]+u(1)+u(1001)+re_[40:],re_[:40]+u(301)+re_[44:],re_[:44]+u(10001)+re_[48:],
                re_[:32]+u(0)+u(0)+u(0)+u(1)+re_[48:],b'N3RD'+re_[4:]]:
        repack({'ranged-attack.bin':bad});check(False)
    repack({'ranged-attack.bin':re_[:32]+u(0)+u(0)+u(0)+u(0)+re_[48:]});check()   # kind 0: the basic attack
    repack({'ranged-attack.bin':re_[:32]+u(1)+u(1000)+u(300)+u(10000)+re_[48:]});check()   # the bounds
    # PQ-423 (D-220): N3RF adds per entry, after the skill hit, the client's
    # cast effect: a key (0-64 printable bytes, an effects clip; a key needs a
    # cast time), then 0 joints without a key, else 1-2 distinct joints, each
    # index + 1 up to 128. This fixture has no effects.bin, so the client
    # refuses any key (and its clip's records are checked where there is
    # one, tests/ranged_attack_live.py); both readers bound the rest alike.
    saved=json.loads(json.dumps(config))
    config['clips'].append(dict(config['clips'][1],markers=[.8,-1]))
    config['profiles'][1].update(attacks=[3],moving=3)
    def effect(**k):return dict(entry(cast_ms=900,cast_effect=dict(dict(clip='bow-cast',joints=[12]),**k)),notice=good['notice'])
    rf=ranged_attack.cook(effect(),config,m['melee'],m['inventory'],m['wear'])
    head=b'N3RF'+u(1)+u(2)+struct.pack('<2f',6,8)+u(900)+u(0)+u(0)+u(0)+u(0)+u(0)+u(0)
    assert rf==head+u(8)+b'bow-cast'+u(1)+u(13)+u(22)+b'Skill Failed - Too far'+u(0),rf
    assert ranged_attack.cook(effect(joints=[-1,127]),config,m['melee'],m['inventory'],m['wear'])[48:72]==u(8)+b'bow-cast'+u(2)+u(0)+u(128)
    for bad in [effect(clip=''),effect(clip='x'*65),effect(clip='tab\there'),effect(clip=7),effect(joints=[]),
                effect(joints=[1,2,3]),effect(joints=[4,4]),effect(joints=[128]),effect(joints=[-2]),effect(joints=[True]),
                effect(extra=1),entry(cast_effect=dict(clip='bow-cast',joints=[12])),dict(effect(),profiles=[dict(effect()['profiles'][0],cast_ms=0)])]:
        try:ranged_attack.cook(bad,config,m['melee'],m['inventory'],m['wear'])
        except ValueError:pass
        else:raise AssertionError(('cooked a bad ranged cast effect',bad))
    m['ranged_attack']=effect();(root/'package.json').write_text(json.dumps(m));main.cook(root,out)
    files={p.name:p.read_bytes()for p in out.iterdir()if p.name not in ('release.bin','release.sha256')}
    assert files['ranged-attack.bin']==rf,files['ranged-attack.bin']
    check(False,True)    # the client: no effects.bin holds 'bow-cast'
    server=subprocess.run(['target/debug/n3e-server','--check-content'],env={**os.environ,'N3E_PACKAGE':str(out)},capture_output=True,text=True)
    assert server.returncode==0,(server.stdout,server.stderr)   # the server checks bounds only
    none=head+u(0)+u(0)+u(22)+b'Skill Failed - Too far'+u(0)
    repack({'ranged-attack.bin':none});check()   # an N3RF entry without a cast effect
    key=lambda k,joints,cast=900:head[:20]+u(cast)+head[24:]+u(len(k))+k+u(len(joints))+b''.join(u(j) for j in joints)+u(22)+b'Skill Failed - Too far'+u(0)
    for bad in [none[:-1],none+b'\0',key(b'',[13]),key(b'k',[]),key(b'k',[1,2,3]),key(b'k',[13,13]),key(b'k',[129]),
                key(b'k'*65,[13]),key(b'a\tb',[13]),key(b'k',[13],cast=0),
                b'N3RE'+none[4:]]:
        repack({'ranged-attack.bin':bad});check(False)
    # PQ-417 (D-222): N3RG adds per entry, after the cast effect, the
    # client's flight: a clip key (0-64 printable bytes; a key needs a cast
    # time), its source joint (index + 1 up to 128) and speed (1-1000), a hit
    # clip key and joint, and a release audio key; all 0 or empty without a
    # flight key. The client refuses a key no effects clip holds (this
    # fixture has none; the clip checks are tests/ranged_attack_live.py's).
    glow=dict(clip='ranged-flight-590',joint=12,speed=77,hit_clip='ranged-hit-550',hit_joint=0,release='ranged-release')
    def flight(**k):
        f={**glow,**k}
        return dict(entry(cast_ms=900,flight={n:v for n,v in f.items() if v is not None}),notice=good['notice'])
    rg=ranged_attack.cook(flight(),config,m['melee'],m['inventory'],m['wear'])
    key_=lambda k:u(len(k))+k
    body=key_(b'ranged-flight-590')+u(13)+struct.pack('<f',77)+key_(b'ranged-hit-550')+u(1)+key_(b'ranged-release')
    assert rg==b'N3RG'+head[4:]+u(0)+u(0)+body+u(22)+b'Skill Failed - Too far'+u(0),rg
    assert ranged_attack.cook(flight(hit_clip=None,hit_joint=None,release=None,joint=-1),config,m['melee'],m['inventory'],m['wear'])[56:]==\
        key_(b'ranged-flight-590')+u(0)+struct.pack('<f',77)+u(0)+u(0)+u(0)+u(22)+b'Skill Failed - Too far'+u(0)
    for bad in [flight(clip=''),flight(clip='x'*65),flight(clip='tab\there'),flight(joint=128),flight(joint=-2),flight(joint=True),
                flight(speed=.5),flight(speed=1001),flight(speed=float('nan')),flight(speed=True),flight(speed=None),
                flight(hit_joint=None),flight(hit_clip=None),flight(hit_clip=''),flight(hit_joint=128),flight(release='x'*65),
                flight(release=7),flight(extra=1),entry(flight=glow),dict(flight(),profiles=[dict(flight()['profiles'][0],cast_ms=0)])]:
        try:ranged_attack.cook(bad,config,m['melee'],m['inventory'],m['wear'])
        except ValueError:pass
        else:raise AssertionError(('cooked a bad ranged flight',bad))
    m['ranged_attack']=flight();(root/'package.json').write_text(json.dumps(m));main.cook(root,out)
    files={p.name:p.read_bytes()for p in out.iterdir()if p.name not in ('release.bin','release.sha256')}
    assert files['ranged-attack.bin']==rg,files['ranged-attack.bin']
    check(False,True)    # the client: no effects.bin holds the flight's clip
    server=subprocess.run(['target/debug/n3e-server','--check-content'],env={**os.environ,'N3E_PACKAGE':str(out)},capture_output=True,text=True)
    assert server.returncode==0,(server.stdout,server.stderr)   # the server checks bounds only
    none=b'N3RG'+head[4:]+u(0)+u(0)+u(0)+u(0)+struct.pack('<f',0)+u(0)+u(0)+u(0)+u(22)+b'Skill Failed - Too far'+u(0)
    repack({'ranged-attack.bin':none});check()   # an N3RG entry without a flight
    def raw(k=b'f',joint=13,speed=77.,hit=b'h',hit_joint=1,release=b'r',cast=900):
        return (b'N3RG'+head[4:20]+u(cast)+head[24:]+u(0)+u(0)+key_(k)+u(joint)+struct.pack('<f',speed)+key_(hit)+u(hit_joint)
                +key_(release)+u(22)+b'Skill Failed - Too far'+u(0))
    for bad in [none[:-1],none+b'\0',raw(cast=0),raw(k=b'',hit=b'',release=b''),raw(k=b'',joint=0,hit=b'',hit_joint=0),
                raw(k=b'',joint=0,speed=0.,hit_joint=0,release=b''),raw(k=b'',joint=0,speed=0.,hit=b'',hit_joint=0),
                raw(joint=129),raw(hit_joint=129),raw(hit=b'',hit_joint=1),raw(speed=.5),raw(speed=1000.5),raw(speed=float('inf')),
                raw(k=b'k'*65),raw(hit=b'h'*65),raw(release=b'r'*65),raw(k=b'a\tb'),b'N3RF'+none[4:]]:
        repack({'ranged-attack.bin':bad});check(False)
    # PQ-467 (D-233): N3RH adds per entry, after the flight, the hold: f32
    # distance (0: none, else 0.5-200) and u32 plane (0 3-D, 1 the ground
    # plane; 0 without a hold); only the server uses it, both readers bound it.
    def held(**k):
        h={**dict(distance=11,plane='xz'),**k}
        return dict(entry(cast_ms=900,hold={n:v for n,v in h.items() if v is not None}),notice=good['notice'])
    rh=ranged_attack.cook(held(),config,m['melee'],m['inventory'],m['wear'])
    plain=u(0)+u(0)+struct.pack('<f',0)+u(0)+u(0)+u(0)
    tail=u(22)+b'Skill Failed - Too far'+u(0)
    assert rh==b'N3RH'+head[4:]+u(0)+u(0)+plain+struct.pack('<f',11)+u(1)+tail,rh
    assert ranged_attack.cook(held(plane='3d',distance=.5),config,m['melee'],m['inventory'],m['wear'])[-len(tail)-8:]==struct.pack('<f',.5)+u(0)+tail
    for bad in [held(distance=.4),held(distance=200.5),held(distance=0),held(distance=float('nan')),held(distance=True),held(distance='11'),
                held(plane='y'),held(plane=1),held(plane=None),held(distance=None),held(extra=1)]:
        try:ranged_attack.cook(bad,config,m['melee'],m['inventory'],m['wear'])
        except ValueError:pass
        else:raise AssertionError(('cooked a bad ranged hold',bad))
    m['ranged_attack']=held();(root/'package.json').write_text(json.dumps(m));main.cook(root,out)
    files={p.name:p.read_bytes()for p in out.iterdir()if p.name not in ('release.bin','release.sha256')}
    assert files['ranged-attack.bin']==rh,files['ranged-attack.bin']
    check()
    raw_h=lambda distance,plane:b'N3RH'+head[4:]+u(0)+u(0)+plain+struct.pack('<f',distance)+u(plane)+tail
    for ok in [raw_h(0.,0),raw_h(.5,0),raw_h(200.,1)]:
        repack({'ranged-attack.bin':ok});check()
    for bad in [rh[:-1],rh+b'\0',raw_h(0.,1),raw_h(.49,1),raw_h(200.5,0),raw_h(-1.,0),raw_h(float('nan'),1),raw_h(float('inf'),1),
                raw_h(11.,2),b'N3RG'+rh[4:]]:
        repack({'ranged-attack.bin':bad});check(False)
    config.clear();config.update(saved)
    del m['ranged_attack']
    print('PASS N3RB/N3RC/N3RD/N3RE/N3RF/N3RG/N3RH ranged basic attacks: both readers take and bound the same profiles, reach, range, cast time and '
          'notice; a cast needs one unshared attack clip with a first marker landing inside the interval (PQ-420); an ammo item '
          'that does not wear, its count within the stack and the ammo notice (PQ-421); a type-2 skill hit, its hit rate, add '
          'damage and add damage plus (PQ-422); a cast effect\'s key and 1-2 distinct joints, a key only with a cast time, and '
          'the client refuses a key no effects clip holds (PQ-423); a flight\'s clip key, source joint, speed, hit clip and '
          'joint and release key, only with a cast time, every field 0 or empty without a key, and the client refuses a key '
          'no effects clip holds (PQ-417); N3RH: a hold of 0 (none, plane 0) or 0.5-200 m on plane 0 or 1 (PQ-467)')
    import consumables
    potion=next(i for i in m['inventory']['items']if i['durability']==0 and i['stack_limit']>1)
    m.update(engine_version=33,protocol_version=26,consumables=[dict(item=potion['id'],health=90,resource=0,delay_ms=500,cooldown_ms=2000)])
    (root/'package.json').write_text(json.dumps(m));main.cook(root,out);check()
    files={p.name:p.read_bytes()for p in out.iterdir()if p.name not in ('release.bin','release.sha256')}
    original=files['consumables.bin']
    for off,value in [(4,0),(4,65),(8,0),(8,99),(12,100001),(20,2001),(24,0),(24,60001)]:
        bad=bytearray(original);struct.pack_into('<I',bad,off,value);repack({'consumables.bin':bad});check(False)
    for bad in [original[:-1],original+b'\0',original[:12]+u(0)+u(0)+original[20:]]:
        repack({'consumables.bin':bad});check(False)
    repack({},['consumables.bin']);check(False)
    for row in [dict(m['consumables'][0],health=-1),dict(m['consumables'][0],item='missing'),dict(m['consumables'][0],delay_ms=True)]:
        try:consumables.cook([row],m['inventory'])
        except ValueError:pass
        else:raise AssertionError('invalid consumable producer')
    print('PASS N3X1 consumable identity, effect/timing bounds, required dependency and hostile readers')
    # Optional original synthetic target marker, hash-owned by the release.
    from common import f
    marker=b'N3TM'+f([2,1.3,.1,1,2,2,3])+u(1)+u(0)+f([0,0,0])+u(1)+u(1)+bytes([0,255,0,255])+u(3)
    for x,z in [(0,0),(1,0),(0,1)]:marker+=f([x,0,z,0,1,0,x,z])
    marker+=u(3)+u(0)+u(1)+u(2)
    m['presentation']['target-marker.bin']='target-marker.bin';(root/'target-marker.bin').write_bytes(marker)
    (root/'package.json').write_text(json.dumps(m));main.cook(root,out);check()
    files={p.name:p.read_bytes()for p in out.iterdir()if p.name not in ('release.bin','release.sha256')}
    for bad in [marker[:-1],marker+b'\0',b'BAD!'+marker[4:]]:
        repack({'target-marker.bin':bad});check(False,True)
    for offset,value in [(4,0),(8,float('inf')),(12,2),(16,-1),(40,11)]:
        bad=bytearray(marker);struct.pack_into('<f',bad,offset,value);repack({'target-marker.bin':bad});check(False,True)
    for offset,value in [(32,0),(32,9),(36,2),(52,513),(56,0),(64,2),(164,2),(168,99)]:
        bad=bytearray(marker);struct.pack_into('<I',bad,offset,value);repack({'target-marker.bin':bad});check(False,True)
    repack({});check()
    (out/'target-marker.bin').write_bytes(marker[:-1]);check(False)
    print('PASS target marker C++/Rust identity and hash protection, bounded native geometry/texture/mode/scale parser')


print('PASS N3V1/N3D2 appearance cross-language identity, dependency bounds, malformed mappings and geometry')
