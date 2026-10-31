"""Opt-in local Tuarek source-space/C++ numeric animation checks."""
import json
import pathlib
import subprocess
import sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools/assetc'))
import ko_character as ko
assets=ko.Assets(pathlib.Path('assets/ko'))
bones=ko.skeleton(assets.get('Chr/upc_ka_tu.n3joint'))
clips=ko.animations(assets.get('Chr/upc_ka_tu.n3anim'))
part=ko.part(assets.get('Item/upc_ka_tu_upper.n3cpart'))
skin=ko.skins(assets.get(part['skin']))[1][0]
def world(frame):
    matrices=[]
    for b in bones:
        local=ko.matrix(ko.sample(b['keys'][0],frame,b['translation']),ko.sample(b['keys'][1],frame,b['rotation']))
        matrices.append(ko.multiply(matrices[b['parent']],local) if b['parent']>=0 else local)
    return matrices
inverses=[ko.inverse(m) for m in world(0)]
def vertex(index,frame):
    matrices=world(frame);p=skin['origins'][index]+[1];out=[0.,0.,0.]
    for joint,weight in zip(skin['joints'][index],skin['weights'][index]):
        m=ko.multiply(matrices[joint],inverses[joint])
        for i in range(3):out[i]+=weight*sum(m[i][j]*p[j] for j in range(4))
    return [out[0],out[1],-out[2]]
reports=[]
locomotion = '--locomotion' in sys.argv
states = [('idle',0),('walk',1 if locomotion else 2),('attack',87),('death',8)]
if locomotion: states += [('run',2),('backward',3)]
base = 'build/ko-01/player' if locomotion else 'build/ko-source/player'
for state,index in states:
    output=subprocess.check_output(['build/client/n3e-asset-check',base+'/cooked-'+state],text=True).splitlines()
    clip=clips[index];maximum=0
    for line in output[1:6]:
        t,*actual=map(float,line.split())
        frame=min(clip['end'],clip['start']+t*clip['fps'])
        expected=vertex(skin['indices'][1],frame)+vertex(skin['indices'][6],frame)
        maximum=max(maximum,max(abs(a-b) for a,b in zip(actual,expected)))
    assert maximum<.001,(state,maximum)
    reports.append(dict(state=state,clip=index,name=clip['name'],max_error_m=maximum,release=output[0]))
pathlib.Path(base+'/verification.json').write_text(json.dumps(reports,indent=2)+'\n')
print(json.dumps(reports,indent=2))
print('PASS male Tuarek race 2,',len(states),'clips, two sampled corners/five times each: source/C++ agreement <1mm')
