#!/usr/bin/env python3
"""Export/rebase bounded absolute edit snapshots; never copies database overrides."""
import argparse,json,pathlib,shutil,struct,tempfile
from common import read,safe
import main,editing

def decode(data):
    if len(data)>32768:raise ValueError('draft bound')
    at=0;out={}
    def varint():
        nonlocal at
        v=0
        for shift in range(0,70,7):
            b=data[at];at+=1;v|=(b&127)<<shift
            if not b&128:return v
        raise ValueError('varint')
    while at<len(data):
        k=varint();tag,typ=k>>3,k&7
        if typ==0:v=varint()
        elif typ==2:n=varint();v=data[at:at+n];at+=n
        elif typ==5:v=struct.unpack_from('<f',data,at)[0];at+=4
        else:raise ValueError('draft wire type')
        if at>len(data):raise ValueError('truncated')
        out.setdefault(tag,[]).append(v)
    return out

def snapshot(path):
    s=decode(read(path));base=s.get(1,[b''])[0].decode('ascii');values=[]
    for raw in s.get(4,[]):
        v=decode(raw);values.append((v.get(1,[b''])[0].decode('ascii'),v.get(2,[0.])[0]))
    if len(base)!=64 or any(x not in '0123456789abcdef' for x in base):raise ValueError('base identity')
    return base,values

def export(source,draft,destination):
    if destination.exists():raise ValueError('export destination must not exist')
    base,values=snapshot(draft)
    with tempfile.TemporaryDirectory() as td:
        cooked=pathlib.Path(td)/'cooked';identity=main.cook(source,cooked)
        if identity!=base:raise ValueError('incompatible base; explicit rebase required')
        m=json.loads((source/'package.json').read_text());ds=editing.descriptors(m)
        if len(values)!=len(ds):raise ValueError('property count')
        for (key,v),(expected,kind,target,_,lo,hi) in zip(values,ds):
            if key!=expected or not lo<=v<=hi or ((kind==6 or kind>=9) and int(v)!=v):raise ValueError('property bounds')
            if kind==0:m['editing']['lighting']=v
            elif kind<=6:
                d=m['editing']['decorations'][target]
                if kind<=3:d['position'][kind-1]=v
                elif kind==4:d['yaw']=v
                elif kind==5:d['scale']=v
            elif kind<=8:
                if 'spawns' not in m['gameplay']:m['gameplay']['spawns']=[[m['gameplay']['spawn_x'],m['gameplay']['spawn_z']]]
                m['gameplay']['spawns'][target][kind-7]=v
            elif kind==9:m['life']['npc_corpse_ticks']=int(v)
            elif kind==10:m['life']['npc_respawn_ticks']=int(v)
        recipe=json.loads((cooked/'recipe.json').read_text())
        staged=pathlib.Path(td)/'source';staged.mkdir()
        for name in recipe['sources']:
            src=safe(source,name);dst=safe(staged,name);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
        (staged/'package.json').write_text(json.dumps(m,indent=2)+'\n')
        main.cook(staged,pathlib.Path(td)/'verified')
        shutil.copytree(staged,destination)
    return main.cook(destination,destination/'cooked')


def varint(n):
    out=bytearray()
    while n>127:out.append((n&127)|128);n>>=7
    return bytes(out)+bytes([n])
def field(tag,b):return varint(tag*8+2)+varint(len(b))+b

def rebase(old_source,new_source,draft,destination):
    if destination.exists():raise ValueError('rebase destination exists')
    base,values=snapshot(draft)
    with tempfile.TemporaryDirectory() as td:
        a,b=pathlib.Path(td)/'old',pathlib.Path(td)/'new'
        if main.cook(old_source,a)!=base:raise ValueError('old base mismatch')
        newhash=main.cook(new_source,b)
        # Automatic rebase accepts only cosmetic dependency changes. Collision,
        # rewards, life, gameplay and registry slot identities must remain equal.
        for name in ['collision.bin','gameplay.bin','progression.bin','life.bin','npc.bin','damage.bin','melee.bin']:
            if (a/name).exists()!=(b/name).exists() or ((a/name).exists() and (a/name).read_bytes()!=(b/name).read_bytes()):raise ValueError('authoritative dependency changed: '+name)
        old=editing.descriptors(json.loads((old_source/'package.json').read_text()))
        new=editing.descriptors(json.loads((new_source/'package.json').read_text()))
        if [x[:3]+x[4:] for x in old]!=[x[:3]+x[4:] for x in new]:raise ValueError('registry changed')
        if len(values)!=len(new):raise ValueError('draft count')
        for (key,v),(k,kind,_,_,lo,hi) in zip(values,new):
            if key!=k or not lo<=v<=hi or ((kind==6 or kind>=9) and v!=int(v)):raise ValueError('draft value')
        data=field(1,newhash.encode())+b''.join(field(4,field(1,k.encode())+varint(21)+struct.pack('<f',v)) for k,v in values)
        destination.write_bytes(data)
    return newhash

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);subs=p.add_subparsers(dest='op',required=True)
    e=subs.add_parser('export');e.add_argument('source',type=pathlib.Path);e.add_argument('draft',type=pathlib.Path);e.add_argument('destination',type=pathlib.Path)
    e=subs.add_parser('rebase');e.add_argument('old_source',type=pathlib.Path);e.add_argument('new_source',type=pathlib.Path);e.add_argument('draft',type=pathlib.Path);e.add_argument('destination',type=pathlib.Path)
    a=p.parse_args()
    print(export(a.source,a.draft,a.destination) if a.op=='export' else rebase(a.old_source,a.new_source,a.draft,a.destination))
