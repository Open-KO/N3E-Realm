"""Optional local-only PMesh oracle: run after cooking Moradon and building client.

Independently parse raw source records; never use the production PMesh importer.
Integer budgets use exact rational arithmetic from the float32 input values.
"""
import struct,pathlib,sys,subprocess
from fractions import Fraction
sys.path.insert(0,'tools/assetc');import ko_shapes
root=pathlib.Path('assets/ko');files={p.name.lower():p for p in (root/'Object').iterdir()}
cache={};expected=[];parts=0
for shape in ko_shapes.load_shapes(root/'Zones/moradon_xmas.opd')['shapes']:
 if ko_shapes.classify(shape) not in ko_shapes.BAKED or any(abs(x)>ko_shapes.SENTINEL_LIMIT for x in shape['position']+shape['scale']):continue
 for part in shape['parts']:
  if not part['mesh'] or not part['textures'] or part['textures'][0].replace('\\','/').split('/')[-1].lower() not in files:continue
  name=part['mesh'].replace('\\','/').split('/')[-1].lower()
  if name not in cache:
   b=files[name].read_bytes();at=4+struct.unpack_from('<i',b)[0];nc,nch,nv,ni,mv,mi=struct.unpack_from('<6i',b,at);at+=24+nv*32
   ix=list(struct.unpack_from('<%dH'%ni,b,at));at+=ni*2
   splits=[struct.unpack_from('<5iB',b,at+i*24) for i in range(nc)];at+=nc*24
   edits=struct.unpack_from('<%di'%nch,b,at);at+=nch*4
   nctrl=struct.unpack_from('<i',b,at)[0];at+=4
   controls=[struct.unpack_from('<fi',b,at+i*8) for i in range(nctrl)]
   cache[name]=(mv,mi,ix,splits,edits,controls)
  v,n,original,splits,edits,controls=cache[name];ix=original.copy();step=0
  metrics=[0.,400.,100.,50.,200.,0.]
  def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]
  for j,(d,_) in enumerate(controls):
   bits=struct.unpack('<I',struct.pack('<f',d))[0]
   lo=struct.unpack('<f',struct.pack('<I',bits-1))[0] if bits else -2**-149
   hi=struct.unpack('<f',struct.pack('<I',bits+1))[0]
   metrics.extend([lo,d,hi])
   if j:
    metrics.extend(f32(controls[j-1][0]+(d-controls[j-1][0])*k/4) for k in range(1,4))
  metrics+=list(reversed(metrics))
  for metric in metrics:
   target=None
   if not controls:target=2147483647
   elif metric<controls[0][0]:target=controls[0][1]
   elif metric>controls[-1][0]:target=controls[-1][1]
   else:
    for (d0,v0),(d1,v1) in zip(controls,controls[1:]):
     if metric<d1:
      target=v0+int((v1-v0)*(Fraction(metric)-Fraction(d0))/(Fraction(d1)-Fraction(d0)));break
   def split():
    global v,n,step
    di,dc,dv,first,to,g=splits[step];v+=dv;n+=di
    for pos in edits[first:first+dc]:ix[pos]=v-1
    step+=1
   if target is not None and target!=v and splits:
    if target>v:
     while step<len(splits) and v<target and v+splits[step][2]<=target:split()
    else:
     while step>0 and target<v:
      step-=1;di,dc,dv,first,to,g=splits[step];n-=di
      for pos in edits[first:first+dc]:ix[pos]=to
      v-=dv
    while step<len(splits) and splits[step][5]:split()
   active=ix[:n]
   assert all(0<=i<v for i in active),(name,metric,v,n)
   h=1469598103934665603
   for t in range(0,n,3):
    for i in (active[t],active[t+2],active[t+1]):h=((h^i)*1099511628211)&((1<<64)-1)
   expected.append((v,n,h))
  parts+=1
trace=subprocess.check_output(['build/client/n3e-lod-check','build/packages/moradon','--trace'],text=True)
pathlib.Path('build/kx/lod-fix').mkdir(parents=True,exist_ok=True)
pathlib.Path('build/kx/lod-fix/topology.txt').write_text(trace)
actual=[tuple(map(int,l.split())) for l in trace.splitlines()]
assert actual==expected,next(((i,a,b) for i,(a,b) in enumerate(zip(actual,expected)) if a!=b),(len(actual),len(expected)))
print('PASS independent raw-file/binary oracle:',parts,'parts,',len(cache),'meshes,',len(expected),'approach/retreat topology hashes')
