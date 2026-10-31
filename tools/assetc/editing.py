"""Bounded typed edit descriptors; all values and identities are package-owned."""
from common import *
import re

def descriptors(m):
    e=m['editing'];game=m['game_id'];out=[]
    # PQ-250: `spawns` (optional) names the spawn points an editor may move;
    # absent, every one. The table holds at most 128 properties, so a zone's
    # whole population names a few or none.
    if not {'lighting','decorations'}<=set(e)<={'lighting','decorations','spawns'}: raise ValueError('editing fields')
    def add(key,kind,target,value,lo,hi):
        if type(value) not in (float,int) or not lo<=value<=hi: raise ValueError('editing value')
        out.append((f'{game}:{key}',kind,target,float(value),lo,hi))
    add('lighting.intensity',0,0,e['lighting'],0,1)
    count(len(e['decorations']),8,1)
    for i,d in enumerate(e['decorations']):
        if set(d)!={'id','position','yaw','scale','visual'} or not re.fullmatch('[a-z][a-z0-9_]{0,24}',d['id']): raise ValueError('decoration fields')
        if d['visual']!='scene.bin': raise ValueError('prepackaged visual required')
        for j,x in enumerate(vector(d['position'],3)): add('decoration.'+d['id']+'.'+['x','y','z'][j],j+1,i,x,-1000,1000)
        add('decoration.'+d['id']+'.yaw',4,i,d['yaw'],-3.141593,3.141593)
        add('decoration.'+d['id']+'.scale',5,i,d['scale'],.05,10)
        add('decoration.'+d['id']+'.visual',6,i,0,0,0)
    sp=m['gameplay'].get('spawns',[[m['gameplay']['spawn_x'],m['gameplay']['spawn_z']]])
    chosen=e.get('spawns',list(range(len(sp))))
    if (not isinstance(chosen,list) or any(type(i) is not int or not 0<=i<min(len(sp),MAX_SPAWNS) for i in chosen)
            or len(set(chosen))!=len(chosen) or chosen!=sorted(chosen)):
        raise ValueError('editing spawns')
    for i in chosen:
        for j,x in enumerate(sp[i]):add(f'spawn.{i}.'+['x','z'][j],7+j,i,x,-1000,1000)
    life=m['life']
    add('npc.corpse_ticks',9,0,life['npc_corpse_ticks'],0,1200)
    # Reference NPC slots carry their own respawn delays; no global override is offered.
    if m.get('npc',{}).get('model')!='reference_melee_v2':
        add('npc.respawn_ticks',10,0,life['npc_respawn_ticks'],1,12000)
    if len({p[0] for p in out})!=len(out):raise ValueError('duplicate edit key')
    if len(out)>128:raise ValueError('editing property bound')
    return out

def cook(m):
    ds=descriptors(m)
    return b'N3T1'+u(len(ds))+b''.join(string(k)+u(kind)+u(target)+f([v,lo,hi]) for k,kind,target,v,lo,hi in ds)
