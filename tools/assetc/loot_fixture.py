"""Original KO-10 loot lab; leaves games/demo and existing realms unchanged."""
import json
from pathlib import Path
import progression_fixture
import main


def cook():
    progression_fixture.cook()
    root=Path('build/loot-source');root.mkdir(parents=True,exist_ok=True)
    import shutil
    for p in Path('build/progression-source').iterdir():
        if p.is_file():shutil.copy2(p,root/p.name)
    m=json.loads((root/'package.json').read_text())
    m.update(engine_version=10,protocol_version=5)
    m['life']={'model':'requested_v1','player_delay_ticks':60,'npc_corpse_ticks':10,'npc_respawn_ticks':20}
    m['gameplay'].update(health=10000,resource=100,cost=1,regen_ticks=1,npc_damage=1,aggro_range=0.05,respawn_ticks=20)
    m['progression']['author']='n3e KO-10 laboratory'
    (root/'package.json').write_text(json.dumps(m,indent=2)+'\n')
    out=Path('build/packages/loot-lab');main.cook(root,out);return out

if __name__=='__main__':print(cook())
