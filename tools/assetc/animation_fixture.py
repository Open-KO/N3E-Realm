#!/usr/bin/env python3
"""Original KO-07 transition lab; --ko uses only already-local optional references."""
import argparse, json, math, shutil, struct
from pathlib import Path
import animation, life_fixture, main, ko_character as ko, ko_player
from common import u, f, string


metadata = ko.animation_metadata

def cook(imported=False):
    life_fixture.cook(imported)
    root = Path('build/ko-07/source-ko' if imported else 'build/ko-07/source')
    shutil.copytree('build/ko-01/source-ko' if imported else 'build/ko-01/source', root, dirs_exist_ok=True)
    m = json.loads((root/'package.json').read_text())
    m['engine_version'] = 8
    m['gameplay'].update(health=1000, npc_health=150, spawns=[[-5,-5]])
    clips=[]
    reports={}
    if imported:
        assets=Path('assets/ko')
        player=Path('build/ko-07/player')
        reports['player']=ko_player.cook(assets,player,locomotion=True,ready=True)
        for state in animation.STATES:
            shutil.copyfile(player/f'player-{state}.bin',root/f'player-{state}.bin')
            clips.append(metadata(reports['player'][state]))
        reports['npc']={}
        for state,index in [('idle',0),('walk',2),('attack',4),('death',10)]:
            target=Path('build/ko-07/npc')/state
            report=ko.convert(assets,'Chr/mob_worm.n3chr',target,index,1.0)
            out=target/'cooked'; main.cook(target,out)
            shutil.copyfile(out/'scene.bin',root/f'npc-{state}.bin')
            reports['npc'][state]=report
            clips.append(metadata(report))
    else:
        # Eleven distinct original clips sharing bind mesh, joints and weights.
        for i,name in enumerate(animation.NAMES):
            target=Path('build/ko-07/synthetic')/name[:-4]
            shutil.copytree('tests/fixtures/legacy-demo',target,dirs_exist_ok=True)
            g=json.loads((target/'fixture.gltf').read_text())
            data=bytearray((target/'fixture.bin').read_bytes())
            offset=g['bufferViews'][8]['byteOffset']
            state=i if i<7 else i-7
            angles={0:[0,.1,0],1:[-.4,.4,-.4],2:[0,-1,0],3:[0,1.3,1.5],4:[-.7,.7,-.7],5:[.4,-.4,.4],6:[.35,.4,.35]}[state]
            struct.pack_into('<12f',data,offset,*[x for a in angles for x in [0,0,math.sin(a/2),math.cos(a/2)]])
            (target/'fixture.bin').write_bytes(data)
            out=target/'cooked'; main.cook(target,out)
            shutil.copyfile(out/'scene.bin',root/name)
            clips.append(dict(duration=1,blend=.2,loop_blend=False,markers=[.5,-1] if state==2 else [-1,-1]))
        prefix=b'N3H1'+u(0)+f([150,20])+u(1)+u(256)+u(128)+bytes(256*128*4)
        record=u(1)+f([0,0])+f([8,8,200,32])+u(0)+f([0,0,1,1])+string('combat')+string('')+u(0xffffffff)+u(0)+u(0)
        (root/'hud.bin').write_bytes(prefix+u(1)+record)
    # The whole-body subset ends attack/death once, even if source loop flags differ.
    for i in [2,3,9,10]: clips[i]['loop_blend']=False
    m['animation']=clips
    m['presentation']={name:name for name in animation.NAMES+['hud.bin']}
    (root/'package.json').write_text(json.dumps(m,indent=2)+'\n')
    (root/'animation-provenance.json').write_text(json.dumps(reports,indent=2)+'\n')
    out=Path('build/packages/animation-ko' if imported else 'build/packages/animation')
    print(main.cook(root,out))
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--ko',action='store_true')
    cook(p.parse_args().ko)
