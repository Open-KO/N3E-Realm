"""Opt-in: source-space numeric checks for all eleven local KO animation clips."""
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0,str(Path('tools/assetc').resolve()))
import ko_character as ko
reports=json.loads(Path('build/ko-07/source-ko/animation-provenance.json').read_text())
results=[]
for role,states in reports.items():
 for state,report in states.items():
    assets=ko.Assets(Path('assets/ko'))
    ch=report['character_metadata'];bones=ko.skeleton(assets.get(ch['joint']))
    part=ko.part(assets.get(ch['parts'][0]));skin=ko.skins(assets.get(part['skin']))[1][0]
    def world(frame):
        out=[]
        for b in bones:
            local=ko.matrix(ko.sample(b['keys'][0],frame,b['translation']),ko.sample(b['keys'][1],frame,b['rotation']))
            out.append(ko.multiply(out[b['parent']],local) if b['parent']>=0 else local)
        return out
    inverse=[ko.inverse(x) for x in world(0)]
    def vertex(index,frame):
        matrices=world(frame);p=skin['origins'][index]+[1];out=[0.,0.,0.]
        for joint,weight in zip(skin['joints'][index],skin['weights'][index]):
            mat=ko.multiply(matrices[joint],inverse[joint])
            for k in range(3):out[k]+=weight*sum(mat[k][j]*p[j] for j in range(4))
        return [out[0],out[1],-out[2]]
    root=Path('build/ko-07/player')/('cooked-'+state) if role=='player' else Path('build/ko-07/npc')/state/'cooked'
    output=subprocess.check_output(['build/client/n3e-asset-check',str(root)],text=True).splitlines()
    clip=report['animations'][report['selected_clip']];maximum=0
    for line in output[1:6]:
        t,*actual=map(float,line.split());frame=min(clip['end'],clip['start']+t*clip['fps'])
        expected=vertex(skin['indices'][1],frame)+vertex(skin['indices'][6],frame)
        maximum=max(maximum,max(abs(a-b) for a,b in zip(actual,expected)))
    assert maximum<.001,(role,state,maximum)
    results.append(dict(role=role,state=state,clip=report['selected_clip'],maximum_error=maximum,release=output[0]))
Path('build/ko-07/numeric-imports.json').write_text(json.dumps(results,indent=2)+'\n')
subprocess.run(['build/client/n3e-animation-check','build/packages/animation-ko'],check=True)
subprocess.run(['build/client/n3e-asset-check','build/packages/animation-ko'],check=True,stdout=subprocess.DEVNULL)
print('PASS all eleven imported clips, source/C++ 5 times x 2 corners; max error',max(r['maximum_error'] for r in results))
