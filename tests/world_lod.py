"""Original topology/format checks, plus optional local binary-oracle comparison."""
import copy,hashlib,json,math,os,pathlib,shutil,struct,subprocess,sys,tempfile
sys.path.insert(0,'tools/assetc')
import ko_lod,ko_tiles,main
from common import u,f,string

# Fans cover precisely one patch, with no inverted/degenerate triangles. The
# perimeter must match the independently specified boundary subdivision.
for level in (2,3):
    for mask in range(16):
        tris=list(ko_lod.fan_cells(level,mask)); area=0;edges={}
        for tri in tris:
            a,b,c=tri; cross=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
            assert cross<0
            area-=cross/2
            for a,b in zip(tri,tri[1:]+tri[:1]):
                edge=tuple(sorted((a,b)));edges[edge]=edges.get(edge,0)+1
        assert area==64 and max(edges.values())==2
        boundary={e for e,n in edges.items() if n==1}
        for side in range(4):
            axis=0 if side in (0,2) else 1;coord=0 if side in (0,3) else 8
            found={tuple(sorted((a[1-axis],b[1-axis]))) for a,b in boundary if a[axis]==b[axis]==coord}
            step=(1 if level==2 else 4) if mask&(1<<side) else (1<<level)
            expected={(i,i+step) for i in range(0,8,step)}
            assert found==expected,(level,mask,side,found)
print('PASS terrain 32 fan variants: area, winding, interior edges and exact shared-edge subdivisions')

# Original A1R5G5B5 texture, all channels and alpha independently known.
pixels=[0xfc00,0x83e0,0x801f,0x7fff]*4
data=struct.pack('<i4s4i',0,b'NTF\x03',4,4,25,1)+struct.pack('<16H',*pixels)
w,h,rgba=ko_tiles.texture(data)
assert (w,h)==(4,4) and rgba[:16]==bytes([255,0,0,255,0,255,0,255,0,0,255,255,255,255,255,0])

with tempfile.TemporaryDirectory(dir='build') as td:
    root=pathlib.Path(td)/'source';out=pathlib.Path(td)/'package'
    shutil.copytree('games/demo',root)
    m=json.loads((root/'package.json').read_text())
    m.update(engine_version=13,protocol_version=7,world='map.bin',exploration=dict(turbo_multiplier=10,fog_start=25.6,fog_end=256,fog_color=[.6,.7,.8],lod='lod.bin'))
    (root/'package.json').write_text(json.dumps(m))
    vs=[[0,0,0,0,1,0,0,0,0,0,0,0],[4,0,0,0,1,0,1,0,0,0,0,0],[0,0,4,0,1,0,0,1,0,0,0,0]]
    world=b'N3W1'+u(16)+u(16)+u(8)+u(1)+bytes([255])*1024+u(3)+b''.join(f(v) for v in vs)+u(3)+u(0)+u(1)+u(2)
    (root/'map.bin').write_bytes(world)
    pm=dict(min_vertices=2,min_indices=3,controls=[(0.,3),(100.,2)],
            splits=[(3,2,1,0,0,1)],edits=[2,4])
    part=dict(center=[0,0,0],radius=4,scale=1,flags=4,levels=[(0.,[0,1,1,0,1,0])],kind=1,
              parent=0,base=0,max_vertices=3,progressive=pm)
    terrain=dict(center=[0,0,0],radius=4,scale=1,flags=2,levels=[(float(i),[0,1,2]) for i in range(33)],kind=2,patch=[0,0])
    built=dict(terrain_lod=dict(origin=[0,0,32],patch_size=32,far_factor=3/512,bias=.6,minimum=2,band=3,width=1),
               parents=[[0,0,0,12,0,0,0,8]],chunks=[part,terrain])
    original=ko_lod.serialize(built);(root/'lod.bin').write_bytes(original);main.cook(root,out)
    def install(data):
        path=out/'world-lod.bin';old=path.read_bytes();path.write_bytes(data)
        index=(out/'release.bin').read_bytes();needle=string('world-lod.bin')+u(len(old))+hashlib.sha256(old).digest()
        assert needle in index
        (out/'release.bin').write_bytes(index.replace(needle,string('world-lod.bin')+u(len(data))+hashlib.sha256(data).digest()))
    def check(good):
        r=subprocess.run(['build/client/n3e-asset-check',str(out)],capture_output=True,text=True)
        assert r.returncode==(0 if good else 1),(r.returncode,r.stderr)
    check(True)
    changes=[lambda b:b['chunks'][0].update(parent=1),lambda b:b['chunks'][0].update(base=3),
             lambda b:b['chunks'][0]['progressive'].update(edits=[99,4]),
             lambda b:b['chunks'][0]['progressive'].update(splits=[(3,2,2,0,0,1)]),
             lambda b:b['chunks'][0]['progressive'].update(splits=[(3,2,1,0,2,1)]),
             lambda b:b['chunks'][0]['progressive'].update(splits=[(3,2,1,0,0,2)]),
             lambda b:b['chunks'][1].update(patch=[1,0]),
             lambda b:b['chunks'].append(copy.deepcopy(b['chunks'][1])),
             lambda b:b['chunks'][0]['progressive'].update(edits=[0,4]),
             lambda b:b['chunks'][0]['progressive'].update(edits=[2,2]),
             lambda b:(b['chunks'][0].update(levels=[(0.,[])]),
                       b['chunks'][0]['progressive'].update(min_indices=0,splits=[(0,2,1,0,0,1)],edits=[0,0]))]
    for change in changes:
        bad=copy.deepcopy(built);change(bad);install(ko_lod.serialize(bad));check(False)
    # Controls that do not rise: the writer refuses them (RQ-195, below), so
    # the client's refusal is shown on forged bytes.
    controls=f([0.])+u(3)+f([100.])+u(2);assert original.count(controls)==1
    install(original.replace(controls,f([10.])+u(3)+f([10.])+u(2)));check(False)
    for data in (original[:-1],original+b'\0'):
        install(data);check(False)
    # A rehashed engine14 index must not bypass the producer's requirement for
    # a player skeleton; previously the renderer could dereference an empty set.
    install(original)
    detail=b'N3D1'+f([1.134464,.5,256])
    (out/'render-detail.bin').write_bytes(detail)
    index=bytearray((out/'release.bin').read_bytes());struct.pack_into('<I',index,8,14)
    at=16
    for _ in range(2):at+=4+struct.unpack_from('<I',index,at)[0]
    count=struct.unpack_from('<I',index,at)[0];prefix=bytes(index[:at]);at+=4;records=[]
    for _ in range(count):
        start=at;length=struct.unpack_from('<I',index,at)[0];at+=4
        name=bytes(index[at:at+length]).decode();at+=length+36
        if name not in ('hud.bin','animation.bin') and not name.startswith(('player-','npc-')):
            records.append(bytes(index[start:at]))
    records.append(string('render-detail.bin')+u(len(detail))+hashlib.sha256(detail).digest())
    (out/'release.bin').write_bytes(prefix+u(len(records))+b''.join(records))
    for command in (['build/client/n3e-asset-check',str(out)],['target/debug/n3e-server','--check-content']):
        result=subprocess.run(command,env={**os.environ,'N3E_PACKAGE':str(out)},capture_output=True,text=True)
        assert result.returncode!=0 and 'requires player presentation' in result.stderr,(command,result.stderr)
print('PASS N3L3 original progressive/terrain fixture, packed-color decode and rehashed malformed metadata')

# PQ-379 (D-201): N3L4 is N3L3 whose kind 1 parts may be alpha parts (flag bit
# 4), each followed by its alpha record (source, destination, state, sort
# point); the writer keeps N3L3 when no part is one. Both the writer and the
# client refuse a record out of its bounds.
import world_chunks
with tempfile.TemporaryDirectory(dir='build') as td:
    root=pathlib.Path(td)/'source';out=pathlib.Path(td)/'package'
    shutil.copytree('games/demo',root)
    m=json.loads((root/'package.json').read_text())
    m.update(engine_version=13,protocol_version=7,world='map.bin',exploration=dict(turbo_multiplier=10,fog_start=25.6,fog_end=256,fog_color=[.6,.7,.8],lod='lod.bin'))
    (root/'package.json').write_text(json.dumps(m))
    vs=[[0,0,0,0,1,0,0,0,0,0,0,0],[4,0,0,0,1,0,1,0,0,0,0,0],[0,0,4,0,1,0,0,1,0,0,0,0]]
    (root/'map.bin').write_bytes(b'N3W1'+u(16)+u(16)+u(8)+u(1)+bytes([255])*1024+u(3)+b''.join(f(v) for v in vs)+u(3)+u(0)+u(1)+u(2))
    pm=dict(min_vertices=3,min_indices=3,controls=[],splits=[],edits=[])
    part=dict(center=[0,0,0],radius=4,scale=1,flags=8|16,levels=[(0.,[0,1,2])],kind=1,parent=0,base=0,max_vertices=3,
              progressive=pm,alpha=dict(source=5,destination=6,state=0x41,point=[1.5,2,-3]))
    terrain=dict(center=[0,0,0],radius=4,scale=1,flags=2,levels=[(float(i),[0,1,2]) for i in range(33)],kind=2,patch=[0,0])
    built=dict(terrain_lod=dict(origin=[0,0,32],patch_size=32,far_factor=3/512,bias=.6,minimum=2,band=3,width=1),
               parents=[[0,0,0,12,0,0,0,8]],chunks=[terrain,part])
    alpha=ko_lod.serialize(built)
    plain=copy.deepcopy(built);plain['chunks'][1]['flags']=8;del plain['chunks'][1]['alpha']
    opaque=ko_lod.serialize(plain)
    assert alpha[:4]==b'N3L4' and opaque[:4]==b'N3L3' and len(alpha)==len(opaque)+24
    assert alpha[-24:]==u(5)+u(6)+u(0x41)+f([1.5,2,-3]) and alpha[4:-24]==opaque[4:].replace(u(8)+u(1)+f([0])+u(3),u(24)+u(1)+f([0])+u(3))
    (root/'lod.bin').write_bytes(alpha);main.cook(root,out)
    r=subprocess.run(['build/client/n3e-asset-check',str(out)],capture_output=True,text=True)
    assert r.returncode==0 and 'world alpha parts 1 first 5 6 65 1.5 2 -3' in r.stdout.splitlines(),(r.stdout,r.stderr)
    for change in [lambda p:p['alpha'].update(source=0),lambda p:p['alpha'].update(source=11),
                   lambda p:p['alpha'].update(destination=0),lambda p:p['alpha'].update(state=0x40),
                   lambda p:p['alpha'].update(state=0x51),lambda p:p['alpha'].update(state=0x5),
                   lambda p:p['alpha'].update(point=[math.nan,0,0]),lambda p:p['alpha'].update(point=[0,0]),
                   lambda p:p['alpha'].update(point=[2e6,0,0]),lambda p:p.update(flags=8),lambda p:p.pop('alpha')]:
        bad=copy.deepcopy(built);change(bad['chunks'][1])
        try:ko_lod.serialize(bad)
        except ValueError:pass
        else:raise AssertionError('wrote a bad alpha part')
    bad=copy.deepcopy(built);bad['chunks'][0].update(flags=2|16,alpha=part['alpha'])
    try:ko_lod.serialize(bad)
    except ValueError:pass
    else:raise AssertionError('wrote an alpha terrain patch')
    def install(data):
        path=out/'world-lod.bin';old=path.read_bytes();path.write_bytes(data)
        index=(out/'release.bin').read_bytes();needle=string('world-lod.bin')+u(len(old))+hashlib.sha256(old).digest()
        assert needle in index
        (out/'release.bin').write_bytes(index.replace(needle,string('world-lod.bin')+u(len(data))+hashlib.sha256(data).digest()))
    def refused(data,reason):
        install(data)
        r=subprocess.run(['build/client/n3e-asset-check',str(out)],capture_output=True,text=True)
        assert r.returncode==1 and reason in r.stderr,(reason,r.returncode,r.stderr)
    record=len(alpha)-24
    patch=lambda at,value:alpha[:at]+u(value)+alpha[at+4:]
    refused(b'N3L3'+alpha[4:],'world part bounds')               # the flag needs N3L4
    refused(patch(record,0),'cooked count')
    refused(patch(record,11),'cooked count')
    refused(patch(record+4,0),'cooked count')
    refused(patch(record+8,0x40),'world alpha part state')       # no blend bit
    refused(patch(record+8,0x51),'world alpha part state')       # point sampling
    refused(patch(record+8,0x45),'world alpha part state')       # culling is the part's flag
    refused(alpha[:record+12]+f([math.nan,0,0]),'cooked finite bound')
    refused(alpha[:-1],'truncated cooked data')
    refused(alpha+b'\0','cooked trailing bytes')
    refused(opaque[:4]+opaque[4:]+alpha[-24:],'cooked trailing bytes')  # a record without the flag
    install(alpha)

    # PQ-382 (D-202): N3L5 is N3L4 whose parts that are not alpha parts may
    # set bit 5 (cut at zero) and bit 6 (unlit); the writer keeps N3L4 / N3L3
    # without them. Neither bit on an alpha part or a terrain patch.
    lit=copy.deepcopy(plain);lit['chunks'][1]['flags']=8|32
    unlit=copy.deepcopy(plain);unlit['chunks'][1]['flags']=8|32|64
    cut=ko_lod.serialize(lit);dark=ko_lod.serialize(unlit)
    flag_word=lambda flags:u(flags)+u(1)+f([0])+u(3)
    assert cut[:4]==dark[:4]==b'N3L5' and len(cut)==len(dark)==len(opaque)
    assert cut[4:]==opaque[4:].replace(flag_word(8),flag_word(40)) and dark[4:]==opaque[4:].replace(flag_word(8),flag_word(104))
    assert ko_lod.serialize(built)[:4]==b'N3L4' and ko_lod.serialize(plain)[:4]==b'N3L3'
    for flags in (8|16|32,8|16|64,8|128):
        bad=copy.deepcopy(built);bad['chunks'][1]['flags']=flags
        try:ko_lod.serialize(bad)
        except ValueError:pass
        else:raise AssertionError('wrote bad part flags 0x%x'%flags)
    for flags in (2|32,2|64):
        bad=copy.deepcopy(plain);bad['chunks'][0]['flags']=flags
        try:ko_lod.serialize(bad)
        except ValueError:pass
        else:raise AssertionError('wrote a terrain patch with flags 0x%x'%flags)
    install(dark)
    r=subprocess.run(['build/client/n3e-asset-check',str(out)],capture_output=True,text=True)
    assert r.returncode==0 and 'world opaque parts cut-zero 1 unlit 1' in r.stdout.splitlines(),(r.stdout,r.stderr)
    install(cut)
    r=subprocess.run(['build/client/n3e-asset-check',str(out)],capture_output=True,text=True)
    assert r.returncode==0 and 'world opaque parts cut-zero 1 unlit 0' in r.stdout.splitlines(),(r.stdout,r.stderr)
    install(b'N3L5'+alpha[4:])                                   # an alpha part in N3L5
    r=subprocess.run(['build/client/n3e-asset-check',str(out)],capture_output=True,text=True)
    assert r.returncode==0 and 'world alpha parts 1 first 5 6 65 1.5 2 -3' in r.stdout.splitlines(),(r.stdout,r.stderr)
    refused(b'N3L4'+dark[4:],'world part bounds')                # the bits need N3L5
    refused(b'N3L5'+opaque[4:].replace(flag_word(8),flag_word(8|128)),'world part bounds')
    refused(b'N3L5'+alpha[4:].replace(flag_word(24),flag_word(24|32)),'world alpha part opaque bits')
    refused(b'N3L5'+alpha[4:].replace(flag_word(24),flag_word(24|64)),'world alpha part opaque bits')
    refused(b'N3L5'+opaque[4:].replace(u(2)+u(33),u(2|32)+u(33),1),'terrain detail variants')
    install(dark)
print('PASS N3L4 alpha parts (PQ-379, D-201): the record after a kind 1 part, N3L3 kept without one, writer and client refuse bad factors, states, points, an alpha terrain patch and a record without its flag')
print('PASS N3L5 opaque part bits (PQ-382, D-202): cut-at-zero and unlit bits on a kind 1 part, N3L4/N3L3 kept without them, writer and client refuse them on an alpha part or a terrain patch and bits above 6')

# RQ-195: the writer refuses a parent, a part head, a level distance or a
# control distance exactly when the client's reader would (read_world_parent:
# cooked floats, both radii within [0, 1e4]; read_world_part: cooked floats,
# radius within [0, 2000], scale within (0, 1000], level distances rising in
# single precision from exactly 0, control distances from above -1). Each
# field's offset is where two accepted values' bytes differ; an accepted value
# is written there and loads, a refused one is refused by the writer and, when
# it packs as a float, forged there to show the client refuses it too.
def f32_step(x,step):  # step float32 values towards +inf
    bits=struct.unpack('<I',struct.pack('<f',x))[0]+(step if x>=0 else -step)
    return struct.unpack('<f',struct.pack('<I',bits))[0]
nan,inf=math.nan,math.inf
past=f32_step(1e6,1)
def parent(k):
    return lambda b,v:b['parents'][0].__setitem__(k,v)
def head(key,k=None):
    def set_(b,v):
        if k is None:b['chunks'][0][key]=v
        else:b['chunks'][0][key][k]=v
    return set_
def level(part,j):
    return lambda b,v:b['chunks'][part]['levels'].__setitem__(j,(v,b['chunks'][part]['levels'][j][1]))
def control(j):
    return lambda b,v:b['chunks'][0]['progressive']['controls'].__setitem__(j,(v,b['chunks'][0]['progressive']['controls'][j][1]))
radius_cases=lambda bound,why:([0.,-0.,bound,1.,bound+bound*1e-8],
                               [(f32_step(bound,1),why),(-1e-30,why),(-1.,why),(nan,'cooked finite bound'),
                                (inf,'cooked finite bound'),(1e39,None)])
cases=[('parent position',parent(0),[1e6,-1e6,3.5],[(past,'cooked finite bound'),(-past,'cooked finite bound'),(nan,'cooked finite bound'),(1e39,None)]),
       ('parent distance radius',parent(3),*radius_cases(1e4,'parent bounds')),
       ('parent radius',parent(7),*radius_cases(1e4,'parent bounds')),
       ('part centre',head('center',1),[1e6,-1e6,2.],[(past,'cooked finite bound'),(nan,'cooked finite bound'),(-inf,'cooked finite bound')]),
       ('part radius',head('radius'),*radius_cases(2000.,'world part bounds')),
       ('part scale',head('scale'),[1000.,1e-30,1.,2.5],
        [(0.,'world part bounds'),(-0.,'world part bounds'),(-1.,'world part bounds'),(f32_step(1000.,1),'world part bounds'),
         (nan,'cooked finite bound'),(1e39,None)]),
       # The terrain patch's 33 levels are 0, 1, ..., 32.
       ('first level distance',level(1,0),[0.,-0.],[(1.,'world LOD bounds'),(-1e-30,'world LOD bounds'),(nan,'cooked finite bound')]),
       ('level distance',level(1,32),[1e6,32.,31.5,31+1e-5],
        [(31.,'world LOD bounds'),(31+1e-7,'world LOD bounds'),(30.,'world LOD bounds'),(past,'cooked finite bound'),(inf,'cooked finite bound')]),
       ('first control distance',control(0),[0.,-.5,f32_step(-1.,1),99.],
        [(-1.,'progressive control'),(-2.,'progressive control'),(100.,'progressive control'),(nan,'cooked finite bound')]),
       ('control distance',control(1),[1e6,100.,1e-30],[(0.,'progressive control'),(-.5,'progressive control'),(past,'cooked finite bound')])]
with tempfile.TemporaryDirectory(dir='build') as td:
    root=pathlib.Path(td)/'source';out=pathlib.Path(td)/'package'
    shutil.copytree('games/demo',root)
    m=json.loads((root/'package.json').read_text())
    m.update(engine_version=13,protocol_version=7,world='map.bin',exploration=dict(turbo_multiplier=10,fog_start=25.6,fog_end=256,fog_color=[.6,.7,.8],lod='lod.bin'))
    (root/'package.json').write_text(json.dumps(m))
    (root/'map.bin').write_bytes(world)
    pm=dict(min_vertices=2,min_indices=3,controls=[(0.,3),(100.,2)],splits=[(3,2,1,0,0,1)],edits=[2,4])
    part=dict(center=[0,0,0],radius=4,scale=1,flags=4,levels=[(0.,[0,1,1,0,1,0])],kind=1,
              parent=0,base=0,max_vertices=3,progressive=pm)
    terrain=dict(center=[0,0,0],radius=4,scale=1,flags=2,levels=[(float(i),[0,1,2]) for i in range(33)],kind=2,patch=[0,0])
    built=dict(terrain_lod=dict(origin=[0,0,32],patch_size=32,far_factor=3/512,bias=.6,minimum=2,band=3,width=1),
               parents=[[0,0,0,12,0,0,0,8]],chunks=[part,terrain])
    (root/'lod.bin').write_bytes(ko_lod.serialize(built));main.cook(root,out)
    current=[(out/'world-lod.bin').read_bytes()];current_good=ko_lod.serialize(built)
    def install(data):
        path=out/'world-lod.bin';old=current[0];path.write_bytes(data);current[0]=data
        index=(out/'release.bin').read_bytes();needle=string('world-lod.bin')+u(len(old))+hashlib.sha256(old).digest()
        assert needle in index
        (out/'release.bin').write_bytes(index.replace(needle,string('world-lod.bin')+u(len(data))+hashlib.sha256(data).digest()))
    def asset_check(data):
        install(data)
        return subprocess.run(['build/client/n3e-asset-check',str(out)],capture_output=True,text=True)
    def write(set_,value):
        b=copy.deepcopy(built);set_(b,value);return ko_lod.serialize(b)
    def parity(name,set_,accepted,refused,prefix):
        a,b=write(set_,accepted[0]),write(set_,accepted[1])
        assert len(a)==len(b) and a!=b,name
        at=next(i for i in range(len(a)) if a[i]!=b[i])//4*4
        assert a[:at]+a[at+4:]==b[:at]+b[at+4:],name
        for value in accepted:
            data=write(set_,value)
            assert data==a[:at]+struct.pack('<f',value)+a[at+4:],(name,value)
            r=asset_check(data)
            assert r.returncode==0,('client refused a written value',name,value,r.stderr)
        for value,why in refused:
            try:write(set_,value)
            except ValueError as e:assert str(e).startswith(prefix),(name,value,e)
            else:raise AssertionError(('wrote a value the client refuses',name,value))
            if why is None:continue  # past the float range: it cannot be forged
            r=asset_check(a[:at]+struct.pack('<f',value)+a[at+4:])
            assert r.returncode==1 and why in r.stderr,(name,value,why,r.stderr)
    for case in cases:parity(*case,'world ')
    # RQ-196: the terrain policy (read_terrain_policy: cooked floats, then in
    # single precision 0.01 <= patch_size <= 1000, 0 < far_factor <= 1,
    # 0 <= bias < 1; minimum and band counts in [1, 64], width in [1, 256]),
    # through world_chunks.policy_bytes, which the chunked writer shares.
    policy=lambda key,k=None:(lambda b,v:b['terrain_lod'][key].__setitem__(k,v) if k is not None
                              else b['terrain_lod'].__setitem__(key,v))
    hundredth=struct.unpack('<f',struct.pack('<f',.01))[0]
    policy_cases=[('terrain origin',policy('origin',0),[0.,1e6,-1e6,-0.],
                   [(past,'cooked finite bound'),(nan,'cooked finite bound'),(-inf,'cooked finite bound'),(1e39,None)]),
                  ('terrain origin z',policy('origin',2),[32.,-1e6],[(-past,'cooked finite bound')]),
                  ('patch size',policy('patch_size'),[32.,1000.,.01,hundredth,500.25],
                   [(f32_step(1000.,1),'terrain detail policy'),(f32_step(hundredth,-1),'terrain detail policy'),
                    (0.,'terrain detail policy'),(1e-30,'terrain detail policy'),(-32.,'terrain detail policy'),
                    (nan,'cooked finite bound'),(1e39,None)]),
                  ('far factor',policy('far_factor'),[3/512,1.,1e-30],
                   [(0.,'terrain detail policy'),(-0.,'terrain detail policy'),(-1e-30,'terrain detail policy'),
                    (f32_step(1.,1),'terrain detail policy'),(inf,'cooked finite bound')]),
                  ('bias',policy('bias'),[.6,0.,-0.,f32_step(1.,-1)],
                   [(1.,'terrain detail policy'),(1-1e-9,'terrain detail policy'),(-1e-30,'terrain detail policy'),
                    (nan,'cooked finite bound'),(1e39,None)])]
    for case in policy_cases:parity(*case,'terrain ')
    # The counts: the bounds load, one past either is refused by the writer
    # and, forged, by the client (the width also sets how many patches the
    # file must hold, so its upper bound is shown at the writer only).
    at=4+24
    assert write(policy('minimum'),2)[at:at+12]==u(2)+u(3)+u(1)
    for key,top,offset in (('minimum',64,0),('band',64,4),('width',256,8)):
        for n in (1,top):
            data=write(policy(key),n);assert data[at+offset:at+offset+4]==u(n),(key,n)
            if key!='width' or n==1:
                r=asset_check(data);assert r.returncode==0,(key,n,r.stderr)
        for n in (0,top+1,-1):
            try:write(policy(key),n)
            except ValueError as e:assert str(e).startswith('terrain policy %s outside'%key),(key,n,e)
            else:raise AssertionError(('wrote a policy count the client refuses',key,n))
            if n<0:continue
            r=asset_check(current_good[:at+offset]+u(n)+current_good[at+offset+4:])
            assert r.returncode==1 and 'cooked count' in r.stderr,(key,n,r.stderr)
print('PASS N3L3 world records (RQ-195): the writer refuses exactly the parents, part heads, level distances and '
      'control distances the client refuses (a float not finite or past 1e6, a parent radius outside [0, 1e4], a '
      'part radius outside [0, 2000], a scale outside (0, 1000], distances not rising in single precision, the first '
      'level not 0, the first control not above -1); an accepted value is written and loads')
print('PASS N3L3 terrain policy (RQ-196): the writer refuses exactly the policies the client refuses (a float not '
      'finite or past 1e6, a patch size outside [0.01, 1000], a far factor outside (0, 1], a bias outside [0, 1) in '
      'single precision, a minimum or band outside [1, 64], a width outside [1, 256]); an accepted value is written '
      'and loads')
