"""Original preserving reward-definition upgrade fixtures."""
import copy,json,shutil,sys
from pathlib import Path
from isolation import once_per_run

@once_per_run
def prepare():
    from party_rewards_live import prepare as base
    source=base().parent/'source'
    result=[]
    for name in ['source','target','next','loot']:
        root=Path('build/ko-completion/reward-upgrades')/name/'source'
        root.mkdir(parents=True,exist_ok=True);shutil.copytree(source,root,dirs_exist_ok=True)
        m=json.loads((root/'package.json').read_text());p=m['progression'];p['ttl']=600
        # This recovery audit deliberately pauses for SQL and offline maintenance.
        # Keep its original actors alive through those pauses and login hashing.
        m['gameplay']['health']=10000
        if name=='source':
            m['engine_version']=24;m['protocol_version']=17;p['model']='contribution_claim_v1';del p['party_rewards']
            p['claim_radius']=3
        else:
            p['claim_radius']=1
            if name in ('next','loot'):p['party_rewards']['bonus_tenths']=4
            if name=='loot':
                m['engine_version']=26;m['protocol_version']=19
                p['model']='contribution_party_loot_v3';p['party_loot']={'radius':50}
        (root/'package.json').write_text(json.dumps(m));sys.path.insert(0,str(Path('tools/assetc').resolve()));import main
        out=root.parent/'package';main.cook(root,out);result.append(out.resolve())
    return result[:3]
