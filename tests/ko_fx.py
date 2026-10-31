"""Original fixtures only: FX layout bounds, texture alpha and timed sampling."""
import copy
import math
import pathlib
import re
import struct
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/'tools/assetc'))
import ko_fx
import ko_fx_bake
import ko_tiles


def pack(fmt,*values):
    return struct.pack('<'+fmt,*values)


def rejects(data):
    try:
        ko_fx.bundle(data)
    except ValueError:
        return
    raise AssertionError('accepted hostile FX')


header=pack('iffB',2,0,0,0)
for slots in (16,26):
    data=header+pack('i',0)*slots+b'\0'
    assert ko_fx.bundle(data)['slots']==slots
    rejects(data[:-1])
    rejects(data+b'\0')
for slots in (0,1,15,17,25,27):
    rejects(header+pack('i',0)*slots+b'\0')
rejects(pack('iffB',3,0,0,0)+pack('i',0)*26+b'\0')
rejects(pack('iffB',2,float('nan'),0,0)+pack('i',0)*16+b'\0')
rejects(pack('iffB',2,0,0,2)+pack('i',0)*16+b'\0')
# A static billboard with an animated texture sequence.
part=pack('ifBBfB',2,0,4,2,0,2)+pack('9f',*[0]*9)+b'\0'+pack('3f',0,0,0)
part+=pack('if',2,30)+b'fx/a'+bytes(256)+pack('IIffI',5,6,0,0,199)
part+=pack('iffBfB4f',1,1,1,0,1,0,0,0,0,0)
data=header+part+pack('i',0)*15+b'\0'
value=ko_fx.bundle(data)
assert len(value['parts'])==1 and value['parts'][0]['textures']==2
for cut in (1,13,18,len(data)-5):rejects(data[:cut])
bad=data.replace(b'fx/a',b'../a');rejects(bad)
frames=ko_fx_bake.sample_part(value['parts'][0],None,lambda name:int(name[-8:-4]),.2,42)
assert frames[0][0][0][1]==0 and frames[1][0][0][1]==1
assert all(not frame for frame in frames[2:]) # nonlooping atlas does not wrap
assert ko_fx_bake.fade(.25,.5,.5,.5)==.5
assert ko_fx_bake.fade(1.25,.5,.5,.5)==.5

# Direct ARGB formats preserve channels and alpha, across native mip levels.
for fmt,pixel,expected in [(21,0x80402010,bytes([64,32,16,128])),(22,0x00402010,bytes([64,32,16,255])),(26,0x8421,bytes([68,34,17,136]))]:
    stride=2 if fmt==26 else 4
    body=pack('H' if stride==2 else 'I',pixel)*80
    texture=pack('i',0)+b'NTF\x03'+pack('4i',8,8,fmt,1)+body
    chain=ko_tiles.mip_chains(texture)[0]
    assert [(w,h)for w,h,_ in chain]==[(8,8),(4,4)]
    assert chain[0][2]==expected*64 and chain[1][2]==expected*16
    assert ko_tiles.texture(texture,4)==(4,4,expected*16)
    try:ko_tiles.mip_chains(texture[:-1])
    except ValueError:pass
    else:raise AssertionError('accepted truncated texture')
print('PASS FX exact layouts, hostile/truncated data, texture timing and native alpha formats')

# PQ-423 (D-220): 00478bc0 reads 26 slots for version 1 too, and past the end
# of a 16-slot file ReadFile leaves the kind at the last value read (0), so a
# version-1 bundle that ends after 16 slots has 16 (1298's arrow.fxb).
one=pack('iffB',1,10,77,0)
assert ko_fx.bundle(one+pack('i',0)*16)['slots']==16 and ko_fx.bundle(one+pack('i',0)*26)['slots']==26
for slots in (15,17,25):rejects(one+pack('i',0)*slots)
rejects(one+pack('i',0)*16+b'\0')
# With a part in slot 15, 00478bc0 would keep its kind for slots 16-25: refused.
last=pack('ifBBfB',2,0,4,2,0,2)+pack('9f',*[0]*9)+b'\0'+pack('3f',0,0,0)+pack('if',2,30)+b'fx/a'+bytes(256)+pack('IIffI',5,6,0,0,199)+pack('iffBfB4f',1,1,1,0,1,0,0,0,0,0)
assert ko_fx.bundle(one+last+pack('i',0)*15)['slots']==16   # a part in slot 0 reads
try:ko_fx.bundle(one+pack('i',0)*15+last)
except ValueError as error:assert 'last slot' in str(error),error
else:raise AssertionError('read a 16-slot version-1 bundle with a part in slot 15')
# A self FX's mesh shape (PQ-430, correcting PQ-423): the mesh part's init
# 0048ea70 sets the shape's position (0041f740 -> 0043b650) to the fresh
# bundle's position (0, 00475060) plus the part's file position (+0x98,
# 0047def0), so the shape file's own position is never drawn and every vertex
# is offset by the part position, turned and scaled with it (00480a70:
# the shape matrix times the part's, 0048f700, 00490120), before 0048fd40
# adds the turned current position (that position plus the part's motion).
# A bundle velocity is drawn only for a clip marked self (move type -1 never
# uses it, 00477590).
import tempfile
import fx_tail_2233_fixture as fx
def ko_string(text):return pack('i',len(text))+text.encode()
def shape_1298(position=(1,2,3),rotation=(0,0,0,1)):
    out=ko_string('s')+pack('3f',*position)+pack('4f',*rotation)+pack('3f',1,1,1)+pack('i',0)*3+pack('I',0)*2+pack('i',1)
    out+=pack('3f',0,0,0)+ko_string('fx\\s\\octahedron.n3pmesh')+pack('17f',*[1]*4+[0]*13)+pack('6I',0,0,0,0,0,0)+pack('i',1)+pack('f',0)
    return out+ko_string('fx\\s\\green.dxt')+pack('5i',0,0,0,0,0)
def mesh_part_(position=(0,0,0),rotation_y=0,scale_vel=0,velocity=(0,0,0),scale=None):
    # A version-5 part carries its scale after the mesh fps (0048ebf0); version 4 is (1, 1, 1).
    scale_vel=scale_vel if isinstance(scale_vel,tuple) else (scale_vel,)*3
    out=pack('ifBBfB',3,0,4 if scale is None else 5,1,10,3)+pack('3f',*velocity)+pack('3f',0,0,0)+pack('3f',0,rotation_y,0)+b'\0'+pack('3f',*position)
    out+=pack('if',0,0)+bytes(260)+pack('I',1)+pack('IIff',5,6,.2,0)
    out+=b'fx/s/s.n3shape'+bytes(260-14)+b'\0'+pack('2f',0,0)+pack('3f',*scale_vel)+b'\0'+pack('3f',0,0,0)+pack('f',0)
    return out+(b'' if scale is None else pack('3f',*scale))
mesh_part=mesh_part_()
arrow=one+mesh_part+pack('i',0)*15
green=pack('i',0)+b'NTF\x03'+pack('4i',4,4,21,1)+pack('I',0xff00ff00)*16
with tempfile.TemporaryDirectory() as tmp:
    root=pathlib.Path(tmp)
    for name,data in [('Data/fx.tbl.csv','"1","2","3","4","5"\n"500","","fx/a.fxb","0","0"\n'.encode()),('fx/a.fxb',arrow),
                      ('fx/s/s.n3shape',shape_1298()),('fx/s/octahedron.n3pmesh',fx.pmesh()),('fx/s/green.dxt',green)]:
        (root/name).parent.mkdir(parents=True,exist_ok=True);(root/name).write_bytes(data)
    import ko_character
    assets=ko_character.Assets(root)
    bundle_=ko_fx.bundle(arrow)
    assert (bundle_['slots'],bundle_['velocity'],[p['kind'] for p in bundle_['parts']])==(16,77,[3]),bundle_
    frames=ko_fx_bake.sample_part(bundle_['parts'][0],assets,lambda name:0,.2,1)
    records=[r for f_ in frames for _key,rs in f_ for r in rs]
    centre=[sum(r[k] for r in records)/len(records) for k in range(3)]
    # The octahedron's centre is its origin. 1298's arrow.fxb: part position
    # (0, 0, 0), so the mesh is drawn at the bundle (the joint), not at the
    # shape file's (1, 2, 3) here (1.782, 3.721, -0.409 in item_arrow).
    assert len(records)==len(frames)*24 and all(abs(a-b)<1e-5 for a,b in zip(centre,(0,0,0))),centre
    def centres(part,limit=.5):
        out=[]
        for f_ in ko_fx_bake.sample_part(ko_fx.bundle(one+part+pack('i',0)*15)['parts'][0],assets,lambda name:0,limit,1):
            rs=[r for _key,batch in f_ for r in batch]
            out.append([sum(r[k] for r in rs)/len(rs) for k in range(3)] if rs else None)
        return out
    close=lambda a,b:all(abs(x-y)<1e-4 for x,y in zip(a,b))
    # A part position p: the shape sits at p and the part's current position
    # starts at p (0048ea70 copies +0x98 to +0x88), so the mesh is at 2p;
    # KO's +z is the engine's -z.
    p=(.25,.5,.75)
    assert all(close(c,(.5,1,-1.5)) for c in centres(mesh_part_(p))),centres(mesh_part_(p))[:2]
    # The part's motion moves only its current position; the shape's p stays.
    for i,c in enumerate(centres(mesh_part_(p,velocity=(0,3,0)))):
        assert close(c,(.5,1+3*(i+1)/30,-1.5)),(i,c)
    # The shape's p is scaled and turned with the vertices (the part matrix
    # 0048f440 builds: rotation 0048f700, scale 00490120), the current
    # position is not: at age t, Ry(t * rate) (p * (1 + t * v)) + p.
    import math
    for i,c in enumerate(centres(mesh_part_(p,rotation_y=2,scale_vel=1))):
        t=i/30;k=1+t;a=2*t
        x,z=p[0]*k,-p[2]*k
        want=(math.cos(a)*x-math.sin(a)*z+p[0],p[1]*k+p[1],math.sin(a)*x+math.cos(a)*z-p[2])
        assert close(c,want),(i,c,want)
    for bad in [(1,float('nan'),0),(101,0,0)]:
        try:ko_fx_bake.sample_part(ko_fx.bundle(one+mesh_part_(bad)+pack('i',0)*15)['parts'][0],assets,lambda name:0,.2,1)
        except ValueError:pass
        else:raise AssertionError(('drew a mesh part at',bad))
    try:ko_fx_bake.cook(assets,dict(clips=dict(c=dict(fx=500,duration=.2)),bindings=[]),root/'e.bin')
    except ValueError as error:assert 'moving' in str(error),error
    else:raise AssertionError('cooked a moving bundle that is not a self FX')
    report=ko_fx_bake.cook(assets,dict(clips=dict(c=dict(fx=500,duration=.2,self=True)),bindings=[]),root/'e.bin')
    assert report['clips']==[dict(key='c',fx=500,sound=0,parts=1,frames=6,slots=16)],report['clips']
    # PQ-417 (D-222): a `flying` clip (the client moves its anchor at the
    # velocity, move type 0) cooks to the self clip's bytes; one cannot be both.
    self_bytes=(root/'e.bin').read_bytes()
    ko_fx_bake.cook(assets,dict(clips=dict(c=dict(fx=500,duration=.2,flying=True)),bindings=[]),root/'e.bin')
    assert (root/'e.bin').read_bytes()==self_bytes
    for bad in [dict(fx=500,duration=.2,self=True,extra=1),dict(fx=500,duration=.2,self=True,flying=True)]:
        try:ko_fx_bake.cook(assets,dict(clips=dict(c=bad),bindings=[]),root/'e.bin')
        except ValueError:pass
        else:raise AssertionError(('cooked a bad clip spec',bad))
    # PQ-431: 1298 draws a mesh vertex v at (v + p) R_part R_dir S + c R_dir + b
    # (row vectors, KO axes): 0048f700 writes the part's rotation and
    # multiplies it by the turn to the bundle direction, 00490120 by the
    # scale (both through 0041dda0, M = M x arg), 0048fd40 writes the
    # translation row. A move type -1 bundle's direction is flattened
    # (00477590, 004786ba), so R_dir is a y turn. With equal x and z scale the
    # cook's records, turned about y by any facing after the cook as the
    # client turns a cast clip, are exactly 1298's vertices.
    def ry(a,v):return (v[0]*math.cos(a)+v[2]*math.sin(a),v[1],-v[0]*math.sin(a)+v[2]*math.cos(a))
    p=(.25,.5,.75);s0=(1.5,.9,1.5);sv=(.5,.25,.5)
    part_=ko_fx.bundle(one+mesh_part_(p,rotation_y=2,scale_vel=sv,velocity=(0,3,0),scale=s0)+pack('i',0)*15)['parts'][0]
    assert (part_['version'],part_['scale'])==(5,[1.5,struct.unpack('<f',pack('f',.9))[0],1.5]),part_
    mesh_=ko_fx_bake.shape(assets,'fx/s/s.n3shape',p)[0]['mesh']
    verts=[mesh_['vertices'][i] for i in mesh_['indices']]
    frames_=ko_fx_bake.sample_part(part_,assets,lambda name:0,.5,1)
    for i,f_ in enumerate(frames_):
        rs=[r for _key,batch in f_ for r in batch];assert len(rs)==len(verts),(i,len(rs))
        t=i/30;S=[s0[k]+sv[k]*t for k in range(3)];c=(p[0],p[1]+3*(i+1)/30,p[2])
        for phi in (0,.7,math.pi/2,2.5,-1.9):
            for v,r in zip(verts,rs):
                w=ry(phi,ry(2*t,(v[0]+p[0],v[1]+p[1],-v[2]+p[2])));cr=ry(phi,c)
                want=[w[k]*S[k]+cr[k] for k in range(3)]
                got=ry(phi,(r[0],r[1],-r[2]))
                assert close(got,want),(i,phi,got,want)
    # Unequal x and z scale (or scale velocity): 1298's result depends on the
    # facing, which a cooked clip cannot carry, so the cook refuses it.
    for bad in [dict(scale=(1.5,.9,1.2)),dict(scale=(1,1,1),scale_vel=(1,0,0)),dict(scale=(2,2,1.6))]:
        try:ko_fx_bake.sample_part(ko_fx.bundle(one+mesh_part_(p,**bad)+pack('i',0)*15)['parts'][0],assets,lambda name:0,.2,1)
        except ValueError as error:assert 'x and z differ' in str(error),error
        else:raise AssertionError(('drew a mesh part with unequal x and z scale',bad))
    (root/'fx/s/s.n3shape').write_bytes(shape_1298(rotation=(0,0,.6,.8)))
    try:ko_fx_bake.shape(assets,'fx/s/s.n3shape',(0,0,0))
    except ValueError:pass
    else:raise AssertionError('drew a rotated FX shape')
    # The shape file's position is never drawn (0048ea70 replaces it): any
    # finite one gives the part's offset; a non-finite one is a malformed
    # file the reader refuses.
    (root/'fx/s/s.n3shape').write_bytes(shape_1298(position=(-40,90,7)))
    assert [s_['offset'] for s_ in ko_fx_bake.shape(assets,'fx/s/s.n3shape',(0,.5,0))]==[(0,.5,0)]
    (root/'fx/s/s.n3shape').write_bytes(shape_1298(position=(1,float('nan'),3)))
    try:ko_fx_bake.shape(assets,'fx/s/s.n3shape',(0,0,0))
    except ValueError:pass
    else:raise AssertionError('read a shape at NaN')
print('PASS PQ-423/PQ-430/PQ-431: a version-1 bundle ending after 16 slots reads as 16 (00478bc0); a mesh part is offset by '
      'its own file position, not its shape file\'s (0048ea70 -> 0041f740), turned and scaled with the vertices '
      '(00480a70, 0048f700, 00490120) before its current position (0048fd40); a bundle velocity is drawn only for a '
      'self or (PQ-417) flying clip; with equal x and z scale the records turned about y by any facing are 1298\'s (v + p) R_part R_dir S '
      '+ c R_dir (PQ-431); a rotated shape, a NaN shape file, a NaN or far part position, unequal x and z scale and '
      'unknown clip fields refused')

# PQ-339: the 2233 layout (0057f0b0, 00589370 and the part loads), original
# synthetic bundles only; the 1298 reader above refuses every one of them.
def path(text):
    return text.encode() + bytes(260 - len(text))


def base(kind, version, base_version, textures=2, fps=30, flags=0x1c7, cycle=(0, 0), texture2=''):
    out = pack('BBf', version, base_version, 0)
    if base_version > 2:
        out += pack('2f', *cycle)
    out += pack('B', kind) + pack('9f', *[0] * 9) + b'\0' + pack('3f', 0, 0, 0)
    out += pack('if', textures, fps) + path('fx\\a\\b_')
    out += (pack('I', 1) + pack('IIff', 5, 2, 0, 0)) if base_version < 2 else pack('IIffI', 5, 2, 0, 0, flags)
    return out + (path(texture2) if base_version > 3 else b'')


def billboard(version=8, base_version=4, v6=0, **kw):
    out = base(2, version, base_version, **kw) + pack('IffBf', 1, 1, 1, 1, 0)
    if version > 2: out += b'\0'
    if version > 3: out += pack('4f', 0, 0, 0, 0)
    if version > 4: out += pack('16f', *[1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1])
    if version > 5: out += pack('B', v6)
    if version > 6: out += b'\0'
    if version > 7: out += b'\0' + pack('3I', 0, 0, 0)
    return out


def particles(version=9):
    out = base(1, version, 3, textures=1, fps=0) + pack('I2f2f3f3ffII3f3f4f', 20, .5, .6, .02, .01, .1, .1, .1,
                                                        -.1, -.1, -.1, .025, 1, 2, 0, 0, -3, 0, 1, 0, .5, 0, 0, 2)
    out += b'\0\0' + pack('3f', -1, -.2, -.3) + b'\0\0' + b'\0' + pack('3I', 0, 0, 0) + pack('2I', 1109393408, 1116471296)
    return out


def mesh(version=8):
    out = base(3, version, 3, textures=0, fps=1) + path('fx\\m.n3shape') + pack('B2f3f', 0, 0, 0, 0, 0, 0)
    return out + b'\1' + pack('3f', 0, 0, 0) + pack('f', 15) + pack('3f', .9, .9, .9) + b'\1\0\0'


def bundle(version, slots, trailing=None, unread=b''):
    out = pack('iffB', version, 0, 0, 0)
    for i in range(8 if version == 0 else 26):
        out += pack('If', slots[i][0], 0) + slots[i][1] if i < len(slots) else pack('i', 0)
    if trailing is None:
        trailing = (b'\0' if version > 1 else b'') + (b'\0' + pack('I', 0) if version > 2 else b'') \
            + (pack('I', 0) + b'\0' if version > 3 else b'') + (b'\0' if version > 4 else b'') \
            + (b'\0' if version > 5 else b'')
    return out + trailing + unread


def rejects_2233(data, text=''):
    try:
        ko_fx.bundle(data, '2233')
    except ValueError as error:
        assert text in str(error), (text, error)
        return
    raise AssertionError('accepted hostile 2233 FX')


main6 = bundle(6, [(2, billboard())])
value = ko_fx.bundle(main6, '2233')
assert (value['version'], value['part_slots'], value['unread'], value['parts'][0]['version'],
        value['parts'][0]['base'], value['parts'][0]['textures'], value['parts'][0]['flags']) == (6, [0], 0, 8, 4, 2, 0x1c7)
rejects(main6)  # the 1298 reader: versions 0-2 only
tail4 = bundle(4, [(3, mesh()), (1, particles())], unread=b'\0\0')
value = ko_fx.bundle(tail4, '2233')
assert [(p['kind'], p['version']) for p in value['parts']] == [(3, 8), (1, 9)] and value['unread'] == 2, value
assert value['parts'][1]['v9'] == [1109393408, 1116471296] and value['parts'][1]['emit_param'] == [0, 0, -3]
assert value['parts'][0]['scale'] == [.8999999761581421] * 3 and value['parts'][0]['v6'] == 1
for cut in (1, 13, 30, len(main6) - 1):
    rejects_2233(main6[:cut])
rejects_2233(tail4 + b'\0\0', 'trailing')            # four unread bytes
rejects_2233(main6 + b'\1', 'trailing')               # an unread byte that is not zero
rejects_2233(bundle(7, []), 'bundle version')
rejects_2233(bundle(6, [(5, b'')]), 'part kind')
rejects_2233(bundle(6, [(2, billboard(version=9))]), 'part/base version')
rejects_2233(bundle(6, [(2, billboard(base_version=5))]), 'part/base version')
rejects_2233(bundle(6, [(2, billboard().replace(b'\x02', b'\x03', 1))]))
rejects_2233(bundle(6, [(2, billboard(flags=0x1c7).replace(pack('II', 5, 2), pack('II', 0, 2)))]), 'blend')
rejects_2233(bundle(6, [(2, billboard().replace(b'fx\\a', b'..\\a'))]), 'unsafe')
assert ko_fx.bundle(bundle(6, [(2, billboard(version=4, base_version=2))]), '2233')['parts'][0]['texture2'] == ''


class Pack:
    namespace = '2145'

    def __init__(self, files):
        self.files = files

    def get(self, name):
        return self.files[name.replace('/', '\\')]  # ko_fx reads its texture names with '/'


def dxt5(alpha0, alpha1, indices):
    """A 4 x 4 DXT5 NTF3 texture (no mips): the alpha end points and 3-bit
    indices, a white colour block (both end points 0xffff)."""
    bits = sum(i << (3 * k) for k, i in enumerate(indices))
    return pack('i', 0) + b'NTF\x03' + pack('4i', 4, 4, ko_tiles.DXT5, 0) + bytes([alpha0, alpha1]) \
        + bits.to_bytes(6, 'little') + pack('HHI', 0xffff, 0xffff, 0) + bytes(4 * 4 * 2)


texel = dxt5(200, 100, list(range(8)) * 2)
try:
    ko_tiles.mip_chains(texel)
except ValueError as error:
    assert 'format' in str(error)
else:
    raise AssertionError('the 1298 path accepted DXT5')
w, h, pixels = ko_tiles.mip_chains(texel, dxt5=True)[0][0]
assert (w, h) == (4, 4) and list(pixels[3::4]) == [200, 100, 185, 171, 157, 142, 128, 114] * 2, list(pixels[3::4])
assert list(dxt5_pixels := ko_tiles.mip_chains(dxt5(100, 200, list(range(8)) * 2), dxt5=True)[0][0][2][3::4]) == \
    [100, 200, 120, 140, 160, 180, 0, 255] * 2, dxt5_pixels
assert pixels[:3] == bytes([255, 255, 255])

# The 2233 main bundle on an FX mesh (ko_fx_bake.appearance_effect with a
# '2233' spec): frames from the spec's own source, no tail; fields 2233 added
# at other values are refused.
import ko_weapon_fx
geometry = dict(copies=[dict(jitter=0, frame_offset=0, vertices=[[0, 0, 0, 0, 0]] * 3)] * 3,
                jitter=[[0, 0, 0], [0, 0, 1]], tail_box=[[0, 0, 0]] * 4, tail_scale=1)
files = {'fx\\main.fxb': main6, 'fx\\a\\b_0000.dxt': texel, 'fx\\a\\b_0001.dxt': texel}
spec = dict(key=1, joint=2, layout='2233', assets=Pack(files), main='fx\\main.fxb', tail=None, tail_id=2,
            trace_color=0xffff00ff, geometry=geometry)
seen = []
entry, clip, _ = ko_fx_bake.appearance_effect(None, lambda n, source: seen.append((n, source)) or len(seen) - 1, spec, 0)
assert (entry['frames'], entry['fps'], entry['blend'], entry['flags'], len(entry['copies']), entry['tails'], clip) == (
    [0, 1], 30, [5, 2], 0x1c7, 3, 0, None), entry
assert [n for n, _ in seen] == ['fx/a/b_0000.dxt', 'fx/a/b_0001.dxt'] and seen[0][1] is spec['assets']
for name, data, text in [
        ('bundle field', main6[:-1] + b'\1', 'bundle fields'),
        ('second texture', bundle(6, [(2, billboard(texture2='fx\\c_'))]), 'main part fields'),
        ('on/off cycle', bundle(6, [(2, billboard(cycle=(0, 1)))]), 'main part fields'),
        ('camera billboard', bundle(6, [(2, billboard(v6=1))]), 'main part fields')]:
    bad = dict(spec, assets=Pack(dict(files, **{'fx\\main.fxb': data})))
    try:
        ko_fx_bake.appearance_effect(None, lambda n, source: 0, bad, 0)
    except ValueError as error:
        assert text in str(error), (name, error)
    else:
        raise AssertionError('accepted ' + name)
print('PASS 2233 FX layout (PQ-339): versions 4 and 6 with billboard, mesh and particle parts read to their last '
      'field, up to 3 unread zero bytes; truncated, unknown kinds/versions, a mismatched type, bad blends and paths, '
      'more or non-zero trailing bytes refused; the 1298 reader refuses them all; DXT5 only on request (8- and '
      '6-level alpha); the 2233 main bundle draws on the FX mesh from its own source, with no tail, and fields '
      '2233 added at other values are refused')

# PQ-341: the 2233 weapon effect's tail (ko_fx_tail_2233), from the original
# synthetic fixture (tools/assetc/fx_tail_2233_fixture.py): two mesh parts,
# a kind-2 and a kind-1 particle part, the bundle's scale flag set.
import subprocess
import tempfile
import fx_tail_2233_fixture as fx
import appearance_effects
from common import u as u32, string as name_bytes

# A no-mip compressed texture as 2233 reads it (00463180): the level, then
# from the w x h / 4 bytes it skips up to 1298's w x h x 2; the 1298 reader
# still asks for the full 16-bit level.
tex = fx.texture()
assert ko_tiles.mip_chains(tex, dxt5=True)[0][0][:2] == (4, 4)
assert ko_tiles.mip_chains(tex, dxt5=True)[0][0][2][:4] == bytes([0, 255, 0, 255])
dxt3 = tex.replace(pack('i', 0x35545844), pack('i', 0x33545844))
assert ko_tiles.mip_chains(dxt3, dxt5=True)[0][0][:2] == (4, 4)
for rest in (4, 32):  # w x h / 4 and w x h x 2
    assert ko_tiles.mip_chains(dxt3[:-8] + bytes(rest), dxt5=True)
for rest in (3, 33):
    try:
        ko_tiles.mip_chains(dxt3[:-8] + bytes(rest), dxt5=True)
    except ValueError as error:
        assert '2233 KO texture size' in str(error)
    else:
        raise AssertionError('accepted a 2233 no-mip texture of %d bytes after its level' % rest)
try:
    ko_tiles.mip_chains(dxt3)
except ValueError as error:
    assert 'truncated' in str(error), error
else:
    raise AssertionError('the 1298 reader took the 2145 no-mip remainder')


def tail_spec(files, scale=1.2):
    geometry_ = dict(geometry, tail_scale=scale, tail_box=[[0, 0, 0], [.4, 0, 0], [0, .6, 0], [0, 0, .1]])
    return dict(spec, assets=fx.Source(dict(files, **{'fx\\main.fxb': main6, 'fx\\a\\b_0000.dxt': texel,
                                                     'fx\\a\\b_0001.dxt': texel})),
                tail=fx.TAIL, geometry=geometry_)


def batches(clip):
    """Each frame's batches of a clip: [(kind, texture, records)]."""
    at = 4 + struct.unpack_from('<I', clip, 0)[0]
    scaled, rate, count = struct.unpack_from('<3I', clip, at)
    at += 12
    out = []
    for _ in range(count):
        frame, (n,) = [], struct.unpack_from('<I', clip, at)
        at += 4
        for _ in range(n):
            kind, texture_, src, dst, flags, records = struct.unpack_from('<6I', clip, at)
            at += 24
            stride = 11 if kind else 9
            values = struct.unpack_from('<%df' % (records * stride), clip, at)
            at += 4 * records * stride
            frame.append((kind, texture_, [values[i:i + stride] for i in range(0, len(values), stride)]))
        out.append(frame)
    assert at == len(clip) and (scaled, rate) == (0, 30)
    return out


def cook(files, scale=1.2):
    seen = []
    entry, key, clip = ko_fx_bake.appearance_effect(
        None, lambda n, source: seen.index(n) if n in seen else seen.append(n) or len(seen) - 1,
        tail_spec(files, scale), 0)
    return entry, key, clip, seen


files = fx.files()
entry, key, clip, seen = cook(files)
report = entry.pop('tail_2233')
assert (entry['tails'], entry['tail_clip'], key) == (2, 'appearance-1-tail', 'appearance-1-tail'), entry
# PQ-342: each particle part's camera-distance rule (40 and 70 m) on its own texture.
rule = dict(count=12, near=40.0, far=70.0, blend=[5, 2], flags=455)
assert report == dict(link_seconds=10.0, frames=600, records=report['records'], parts=[[3, 8], [3, 8], [1, 9], [1, 9]],
                      scale=True, thinning=[dict(rule, texture=4), dict(rule, texture=5)]), report
assert seen[2:] == ['fx/object/a/green_0000.dxt', 'fx/object/b/green_0000.dxt', 'fx/particle/green_0000.dxt',
                    'fx/particle/lime_0000.dxt'], seen
frames = batches(clip)
assert len(frames) == 600
# The meshes: 8 triangles each, white at full alpha, for the first link half only.
for n, frame in enumerate(frames):
    meshes = [b for b in frame if b[0] == 0]
    assert [len(b[2]) for b in meshes] == ([24, 24] if n < 300 else []), (n, [len(b[2]) for b in meshes])
    for b in meshes:
        assert all(r[5:] == (1, 1, 1, 1) for r in b[2])
radius = .08


def extent(frame, part):
    """The largest distance of a mesh part's vertices from the tail point."""
    return max(math.sqrt(sum(x * x for x in r[:3])) for r in frames[frame][part][2])


# 0059a6f0 at 15 frames a second: the scale keys (1, then 0.5 for keys
# 20-29: ages 1.33-2 s) times the part's 0.9 times the target scale 1.2;
# a turn keeps the distance. The frames wrap after 50 (3.33 s, 100 samples).
for n in (0, 1, 7, 33, 38):
    assert abs(extent(n, 0) - radius * .9 * 1.2) < 1e-5, (n, extent(n, 0))
for n in (41, 45, 57):
    assert abs(extent(n, 0) - radius * .9 * 1.2 * .5) < 1e-5, (n, extent(n, 0))
# Between keys 0044b450 blends: age 1.3 s is frame 19.5, half way to 0.5.
assert abs(extent(39, 0) - radius * .9 * 1.2 * .75) < 1e-5, extent(39, 0)
assert abs(extent(141, 0) - extent(41, 0)) < 1e-6 and abs(extent(101, 0) - extent(1, 0)) < 1e-6
# At 40 frames a second the second mesh dips for ages 0.5-0.75 s.
assert abs(extent(18, 1) - radius * .7 * 1.2 * .5) < 1e-5 and abs(extent(12, 1) - radius * .7 * 1.2) < 1e-5
# The turn: at age 0 the octahedron's first vertex lies on +x; one sample later
# (age 1/30) Rx x Ry x Rz of -0.3 rad moves it off the axis, and the +9 rad/s
# mesh turns it the other way.
first = [r[:3] for r in frames[0][0][2]]
assert any(abs(p[0] - radius * 1.08) < 1e-6 and abs(p[1]) < 1e-6 and abs(p[2]) < 1e-6 for p in first)
assert not any(abs(abs(p[0]) - radius * 1.08) < 1e-6 for p in (r[:3] for r in frames[1][0][2]))
a0, b0 = frames[1][0][2][0][:3], frames[1][1][2][0][:3]
assert abs(a0[0] / (.9 * 1.2) - b0[0] / (.7 * 1.2)) < 1e-5 and abs(a0[1] / .9 - b0[1] / .7) > 1e-3


def particles_of(frame, part):
    return [r for r in frames[frame][part][2]] if len(frames[frame]) > part else []


# Particles: emitted for the link's first half, finished in its second
# (their life 0.2-0.3 s plus 0.1 s in and 0.2 s out).
assert particles_of(0, 2) and particles_of(299, 2) and not any(frames[n] for n in range(320, 600))
assert all(r[10] < 10 for frame in frames for b in frame if b[0] for r in b[2])
# The kind-2 part: each particle starts within 0.03 x 1.2 of the tail point
# and heads for its target 3 m up (+z turned to +y) at 0.5 m/s, less the
# gravity drop; its size is 0.1-0.12 x 1.2.
born = [r for r in particles_of(0, 2) if r[10] == 0]
assert born and all(abs(r[0]) <= .036 + 1e-6 and abs(r[1]) <= .036 + 1e-6 for r in born), born
assert all(.12 - 1e-6 <= r[3] <= .144 + 1e-6 for r in born), born
later = [r for r in particles_of(6, 2) if r[10] == 0]
assert later and all(r[1] > born[0][1] + .05 for r in later), (born, later)


def rise(files_, part):
    """The first particle's height after 6 samples (0.2 s)."""
    _, _, clip_, _ = cook(files_, 2.0)
    frames_ = batches(clip_)
    return [r for r in frames_[6][[b for b in range(len(frames_[6])) if frames_[6][b][0]][part - 2]][2]
            if r[10] == 0][0][1]


# The target scale reaches a kind-1 particle's velocity, not a kind-2 one's
# (005915e0 sets it after the scale): with the scale flag off the kind-2
# particle rises as far, the kind-1 particle half as far at scale 2.
unscaled = fx.files(fx.bundle(fx.parts(), scale=0))
assert abs(rise(files, 2) - rise(unscaled, 2)) < .02, (rise(files, 2), rise(unscaled, 2))
assert rise(files, 3) > 1.5 * rise(unscaled, 3) > 0, (rise(files, 3), rise(unscaled, 3))

# The client reads the cooked N3E2 with its 20 s tail clip; a 20.7 s clip
# (600 samples at 29 a second) and 601 samples are past its bounds.
CHECK = pathlib.Path(__file__).resolve().parents[1] / 'build/client/n3e-effects-check'
textures = u32(6) + b''.join(u32(4) + u32(4) + bytes([0, 255, 0, 255]) * 16 for _ in range(6))
n3ef = b'N3EF' + textures + u32(1) + clip + u32(0)
n3e2 = appearance_effects.n3e2(n3ef, [entry], 1)
body = clip[len(name_bytes(key)):]
with tempfile.TemporaryDirectory() as tmp:
    def reads(blob):
        p = pathlib.Path(tmp) / 'effects.bin'
        p.write_bytes(blob)
        return subprocess.run([str(CHECK), str(p)], capture_output=True, text=True).returncode == 0
    assert reads(n3e2)
    slow = clip[:len(name_bytes(key)) + 4] + u32(29) + clip[len(name_bytes(key)) + 8:]
    assert not reads(b'N3EF' + textures + u32(1) + slow + u32(0))
    longer = clip[:len(name_bytes(key)) + 8] + u32(601) + clip[len(name_bytes(key)) + 12:] + u32(0)
    assert not reads(b'N3EF' + textures + u32(1) + longer + u32(0))

# What the cook cannot confirm or draw it refuses, naming it.
mesh_a, mesh_b, kind2, kind1 = (p for _, p in fx.parts())
shape_rot = fx.shape().replace(fx.pack('i', 0) + fx.pack('i', 0) + fx.pack('iif', fx.KEYS, 0, 30.),
                               fx.pack('i', 0) + fx.pack('iif', 1, 1, 30.) + fx.pack('4f', 0, 0, .6, .8)
                               + fx.pack('iif', fx.KEYS, 0, 30.))
for name, parts_, text, change in [
        ('a billboard part', [(2, billboard())], 'part kind 2', {}),
        ('bundle motion', fx.parts(), 'bundle motion', dict(velocity=1.)),
        ('bundle life', fx.parts(), 'bundle motion', dict(life=1.)),
        ('a y-facing quad', [(1, fx.particle_part(2, (0, 0, 3), .5, v7=1))], 'y-facing quad', {}),
        ('an extra turn', [(1, fx.particle_part(2, (0, 0, 3), .5, v8=(1, 0, 0, 0)))], 'extra turn', {}),
        ('a direction off +y', [(1, fx.particle_part(1, (360,), .4, direction=(0, 0, 1)))], 'direction', {}),
        ('two textures', [(1, fx.particle_part(1, (360,), .4, textures=2))], 'texture sequence', {}),
        ('a uv scroll', [(3, fx.mesh_part(fx.SHAPES[0], (9, 9, 9), .9, 15, uvdir=1))], 'uv scroll', {}),
        ('a camera turn', [(3, fx.mesh_part(fx.SHAPES[0], (9, 9, 9), .9, 15, v7=1))], 'uv scroll', {}),
        ('the other fade', [(3, fx.mesh_part(fx.SHAPES[0], (9, 9, 9), .9, 15, v8=1))], 'uv scroll', {}),
        ('a stopping mesh', [(3, fx.mesh_part(fx.SHAPES[0], (9, 9, 9), .9, 15, wrap=0))], 'stops on its last', {}),
        ('no whole cycles', [(3, fx.mesh_part(fx.SHAPES[0], (9, 9, 9), .9, 7))], 'no link', {}),
        ('shape rotation keys', [(3, mesh_a)], 'translation or rotation keys', dict(shape=shape_rot))]:
    shape_ = change.pop('shape', None)
    files_ = fx.files(fx.bundle(parts_, **change))
    if shape_:
        files_[fx.SHAPES[0]] = shape_
    try:
        cook(files_)
    except ValueError as error:
        assert text in str(error), (name, error)
    else:
        raise AssertionError('cooked a tail with ' + name)
print('PASS 2233 weapon effect tail (PQ-341): the synthetic tail cooks to a 20 s clip of two 10 s links (whole '
      'cycles of both meshes, 50 frames at 15 and 40 a second); its meshes turn by Rx Ry Rz of age x rotation, '
      'scaled by their keys (blended, wrapping after 50 frames) x part scale x target scale, only in the first '
      'half; its particles rise toward the turned target (kind 2, unscaled velocity) or spread (kind 1, scaled), '
      'are emitted for the first half and finish in the second; the client reads the clip and refuses 20.7 s '
      'and 601 samples; no-mip compressed textures read as 2233 does; billboard parts, bundle motion and life, '
      'y-facing quads, extra turns, directions other than +y, texture sequences, uv scrolls, camera turns, the other '
      'fade, stopping meshes, meshes with no whole cycles in 10 s and shape rotation keys are refused')

# PQ-342: 2233's camera-distance particle thinning (00592900, assembly
# 005929ac-00592a37) as N3E4 rules on the tail clip. With a rule the cook
# writes every emission as a candidate (the ones the full pool refuses drawn
# from a second generator), and the client takes them by the rule.


def thin_model(frames_, rule_, rate, schedule, stop=10.0):
    """The rule in Python: per sample the births of the rule's batches drawn
    (record order) and the target, with the camera at each (sample, distance)
    of `schedule` from that sample on."""
    taken, alive, out = set(), 0, []
    for j, frame_ in enumerate(frames_):
        d = [dist for at, dist in schedule if j >= at][-1]
        target = rule_['count'] if d < rule_['near'] else int((rule_['far'] - d) / rule_['far'] * rule_['count'])
        births = [round(r[10] * rate) for kind, texture_, records in frame_ if kind and texture_ == rule_['texture']
                  for r in records]
        if j in births and j / rate < stop and alive <= target and alive < rule_['count']:
            taken.add(j)
        alive = sum(b in taken for b in births)
        out.append((target, [] if target == 0 else [b for b in births if b in taken]))
    return out


# Without a rule (the version-6 byte set, 00592900's switch) the cook writes
# PQ-341's stream; with one, the candidates the client takes within near are
# exactly those records, so drawing at short range is unchanged. The parts'
# pools are cut to 6 here, so the full pool refuses emissions the rule's
# candidates still carry.


def small(v6):
    return fx.bundle(fx.parts()[:2] + [(1, fx.particle_part(2, (0, 0, 3), .5, count=6, v6=v6)),
                                       (1, fx.particle_part(1, (360,), .4, texture=fx.LIME, count=6, v6=v6))])


plain_entry, _, plain_clip, _ = cook(fx.files(small(1)))
thin_entry, _, thin_clip, _ = cook(fx.files(small(0)))
assert plain_entry['tail_2233']['thinning'] == [], plain_entry['tail_2233']
plain_frames, thin_frames = batches(plain_clip), batches(thin_clip)
pooled, candidates = (sum(len(b[2]) for frame_ in f_ for b in frame_ if b[0]) for f_ in (plain_frames, thin_frames))
assert candidates > pooled, (candidates, pooled)
for texture_ in (4, 5):
    r_ = dict(rule, texture=texture_, count=6)
    drawn = thin_model(thin_frames, r_, 30, [(0, 5.0)])
    assert all(t == 6 for t, _ in drawn)
    for j, (frame_, plain_frame) in enumerate(zip(thin_frames, plain_frames)):
        got = [r for kind, t, records in frame_ if kind and t == texture_ for r in records
               if round(r[10] * 30) in set(drawn[j][1])]
        want = [r for kind, t, records in plain_frame if kind and t == texture_ for r in records]
        assert got == want, (texture_, j, len(got), len(want))
    assert max(len(d) for _, d in drawn) == 6

# The client applies the rule as the model does (build/client/n3e-effects-check
# --thin): one link at 5 m (within near: the pool alone), 45 m (trunc(12 x 25 /
# 70) = 4), 65 m (0: none drawn) and 100 m (negative: none taken, the taken
# ones drawn till they die).
rules = [dict(r, clip=key) for r in report['thinning']]
n3e4 = appearance_effects.n3e4(n3ef, [entry], [], rules, 1)
assert n3e4[:4] == b'N3E4'
schedule = [(0, 5.0), (100, 45.0), (200, 65.0), (250, 100.0), (280, 45.0)]
with tempfile.TemporaryDirectory() as tmp:
    path_ = pathlib.Path(tmp) / 'effects.bin'
    path_.write_bytes(n3e4)
    run = subprocess.run([str(CHECK), str(path_), '--thin', key] + ['%d:%g' % s_ for s_ in schedule],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    client_ = {}
    for line in run.stdout.splitlines():
        k, j, t, d = re.match(r'^THIN rule=(\d+) sample=(\d+) target=(-?\d+) drawn=([\d,]*)$', line).groups()
        client_[int(k), int(j)] = (int(t), [int(b) for b in d.split(',')] if d else [])
for k, r_ in enumerate(report['thinning']):
    model = thin_model(frames, r_, 30, schedule)
    assert [client_[k, j] for j in range(600)] == model, k
    assert {t for t, _ in model} == {12, 4, 0, -5}, {t for t, _ in model}
    within = max(len(d) for t, d in model[:100])
    thinned = max(len(d) for t, d in model[120:200])
    assert within > 5 >= thinned > 0 and not any(d for t, d in model[200:250]), (within, thinned)
    assert model[250][1] and not model[275][1] and model[290][1], (model[250], model[275], model[290])

# N3E4's serializer and the client refuse malformed rules.
good = dict(rules[0])
for name, change, text in [
        ('an unknown clip', dict(clip='missing'), 'rule clip'),
        ('a texture past the file', dict(texture=6), 'rule material'),
        ('a blend of 0', dict(blend=[0, 2]), 'rule material'),
        ('a flag past 11 bits', dict(flags=0x800), 'rule material'),
        ('a pool of 0', dict(count=0), 'count'),
        ('a pool of 1025', dict(count=1025), 'count'),
        ('near 0', dict(near=0.0), 'rule distance'),
        ('far past 1000 m', dict(far=1000.5), 'rule distance'),
        ('a NaN distance', dict(near=float('nan')), 'rule distance'),
        ('no batch of that material', dict(texture=0), 'rule batch')]:
    try:
        appearance_effects.n3e4(n3ef, [entry], [], [dict(good, **change)], 1)
    except ValueError as error:
        assert text in str(error), (name, error)
    else:
        raise AssertionError('serialized a rule with ' + name)
for name, args, text in [
        ('no rules', ([entry], [], []), 'count'),
        ('a rule twice', ([entry], [], [good, good]), 'duplicate'),
        ('a clip no tail names', ([dict(entry, tails=0, tail_clip='')], [], [good]), 'rule clip')]:
    try:
        appearance_effects.n3e4(n3ef, *args, 1)
    except ValueError as error:
        assert text in str(error), (name, error)
    else:
        raise AssertionError('serialized ' + name)
# A bound clip and duplicate births, which only bytes can say past the serializer.
bound = b'N3EF' + textures + u32(1) + clip + u32(1) + u32(1) + name_bytes('cast') + u32(0) + u32(0) + u32(1) \
    + name_bytes(key)
try:
    appearance_effects.n3e4(bound, [entry], [], [good], 1)
except ValueError as error:
    assert 'rule clip' in str(error), error
else:
    raise AssertionError('serialized a rule on a bound clip')
section_at = n3e4.rindex(name_bytes(key) + u32(4))


def hostile_rule(offset, value, fmt='<I'):
    at = section_at + len(name_bytes(key)) + offset
    return n3e4[:at] + struct.pack(fmt, value) + n3e4[at + struct.calcsize(fmt):]


with tempfile.TemporaryDirectory() as tmp:
    def refused(blob):
        p_ = pathlib.Path(tmp) / 'effects.bin'
        p_.write_bytes(blob)
        run_ = subprocess.run([str(CHECK), str(p_)], capture_output=True, text=True)
        reasons.append(run_.stderr.strip())
        return run_.returncode != 0
    reasons = []
    assert not refused(n3e4)
    # Truncated, a trailing byte, the section missing, a texture past the
    # file, blend 0, flag 0x800, pools 0 and 1025, near 0, far past 1000 m, a
    # NaN, a material no batch has, the rules twice, a clip a binding plays.
    hostile = [n3e4[:-1], n3e4 + b'\0', b'N3E4' + n3e4[4:section_at - 4],
               hostile_rule(0, 6), hostile_rule(4, 0), hostile_rule(12, 0x800), hostile_rule(16, 0),
               hostile_rule(16, 1025), hostile_rule(20, 0.0, '<f'), hostile_rule(24, 1000.5, '<f'),
               hostile_rule(20, float('nan'), '<f'), hostile_rule(0, 0),
               n3e4[:section_at - 4] + u32(4) + n3e4[section_at:] * 2,
               b'N3E4' + bound[4:] + n3e4[len(n3ef):]]
    assert [refused(h) for h in hostile] == [True] * len(hostile), reasons
    assert reasons[1:] == ['truncated cooked data', 'cooked trailing bytes', 'truncated cooked data'] + [
        'appearance tail particle rule material', 'cooked count', 'appearance tail particle rule material'] + [
        'cooked count'] * 2 + ['appearance tail particle rule distance'] * 2 + [
        'cooked finite bound', 'appearance tail particle rule batch', 'duplicate appearance tail particle rule',
        'appearance tail particle rule clip'], reasons
    # A thinned batch's candidate with no birth (-1, which other batches may
    # hold), and two candidates of one birth in a frame.
    at = clip.index(struct.pack('<6I', 1, 4, 5, 2, 455, 1)) + 24 + 40
    no_birth = clip[:at] + struct.pack('<f', -1.0) + clip[at + 4:]
    at = clip.index(struct.pack('<6I', 1, 4, 5, 2, 455, 2)) + 24
    twice = clip[:at + 44 + 40] + clip[at + 40:at + 44] + clip[at + 44 + 44:]
    for bad in (no_birth, twice):
        assert refused(b'N3E4' + n3ef[4:].replace(clip, bad) + n3e4[len(n3ef):])
        assert reasons[-1] == 'appearance tail particle rule candidates', reasons[-1]
        assert not refused(b'N3EF' + n3ef[4:].replace(clip, bad))

# The cook refuses what the rule cannot carry, naming it: a thinned part's
# batch above 1, a distance past 1000 m or not finite, and two thinned parts
# with one texture and render state.
for name, parts_, text in [
        ('a batch of 2', [(1, fx.particle_part(2, (0, 0, 3), .5, batch=2))], 'batch other than 1'),
        ('far past 1000 m', [(1, fx.particle_part(2, (0, 0, 3), .5, v9=(fx.bits(40), fx.bits(1001))))],
         'camera distance'),
        ('an infinite near', [(1, fx.particle_part(2, (0, 0, 3), .5, v9=(fx.bits(math.inf), fx.bits(70))))],
         'camera distance'),
        ('one material twice', [(1, fx.particle_part(2, (0, 0, 3), .5)), (1, fx.particle_part(1, (360,), .4))],
         'sharing its texture')]:
    try:
        cook(fx.files(fx.bundle(parts_)))
    except ValueError as error:
        assert text in str(error), (name, error)
    else:
        raise AssertionError('cooked a thinned tail with ' + name)
# Zero distances are 00592900's defaults, 10 and 30 m (0058ef60 zeroes them;
# a part before version 9 has none); with the version-6 byte two parts may
# share a material, and a batch of 2 is drawn as before.
zero, _, _, _ = cook(fx.files(fx.bundle([(1, fx.particle_part(2, (0, 0, 3), .5, v9=(0, 0)))])))
assert [(r['near'], r['far']) for r in zero['tail_2233']['thinning']] == [(10.0, 30.0)], zero['tail_2233']
free, _, _, _ = cook(fx.files(fx.bundle([(1, fx.particle_part(2, (0, 0, 3), .5, v6=1, batch=2)),
                                         (1, fx.particle_part(1, (360,), .4, v6=1))])))
assert free['tail_2233']['thinning'] == [], free['tail_2233']
print(f"PASS 2233 tail camera-distance thinning (PQ-342): each particle part of the synthetic tail carries "
      f"00592900's rule (pool 12, near 40 m, far 70 m) as an N3E4 rule on its batch; the version-6 byte keeps "
      f"PQ-341's stream and no rule; with the rule the cook writes every emission as a candidate and, within near, "
      f"one link's (a chain's first) candidates taken are exactly PQ-341's records (pools cut to 6 so the pool refuses some: {candidates} "
      f"candidates for {pooled} records); the client (n3e-effects-check --thin) takes and draws the same candidates "
      f"as the Python model for one link at 5, 45, 65, 100 and 45 m (targets 12, 4, 0, -5), none drawn at 0 and none "
      f"taken past far; zero distances are 10 and 30 m; malformed rules are refused by the serializer and the client, "
      f"and batches above 1, distances past 1000 m or not finite and shared materials by the cook")
