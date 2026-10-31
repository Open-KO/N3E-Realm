"""Disposable original progression laboratory. Never modifies games/demo."""
import json
import pathlib
import shutil
import main


def cook():
    root=pathlib.Path('build/progression-source')
    root.mkdir(parents=True,exist_ok=True)
    for p in pathlib.Path('tests/fixtures/legacy-demo').iterdir():
        if p.is_file(): shutil.copy2(p,root/p.name)
    m=json.loads((root/'package.json').read_text())
    m['engine_version']=9;m['protocol_version']=4
    r=m['gameplay']
    r.update(npc_health=100,damage=60,slots=2,starting_items=0,reward_xp=10)
    m['progression']={'model':'contribution_claim_v1','stat_policy':'fixed_v1',
        'curve':m['game_id']+':curve/lab','item':r['item'],'origin':'original synthetic',
        'author':'n3e KO-09 laboratory','revision':1,'thresholds':[0,20,50,90,140,200,270,350,440,540],
        'capacity':r['slots'],'starting':r['starting_items'],'npc_level':1,'base_xp':10,
        'radius':50,'claim_radius':3,'ttl':120}
    (root/'package.json').write_text(json.dumps(m,indent=2)+'\n')
    out=pathlib.Path('build/packages/progression-lab')
    main.cook(root,out)
    return out

if __name__=='__main__': print(cook())
