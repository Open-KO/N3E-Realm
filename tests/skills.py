"""Original bounded skill/audio fixtures; no KO assets required."""
import copy,io,json,pathlib,struct,subprocess,sys,tempfile,wave
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools/assetc'))
import skills,ko_audio,audio_spatial
from common import f,u
base=dict(id='demo:skill/heal',label='Heal',**{'class':'demo:class/test'},level=1,cost=5,cast_ms=1500,cooldown_ms=2000,range=25,target=1,amount=15,survival=80,attribute=4,resistance=0,weapons=[],animation=0,cast_effect='cast',cast_joints=[12,7],target_effect='heal',target_joint=-1)
# PQ-465 (D-232): Moradon's reach, as games/moradon/skills.json carries it.
moradon_reach=json.loads(pathlib.Path('games/moradon/skills.json').read_text())['reach']
config=dict(archetype='demo:class/test',label='Test',reach=moradon_reach,skills=[base,{**base,'id':'demo:skill/strike','target':2}]);valid=skills.cook(config)
with tempfile.TemporaryDirectory(prefix='n3e-skills-')as root:
 path=pathlib.Path(root)/'skills.bin'
 def native(data,good):
  path.write_bytes(data);p=subprocess.run(['build/client/n3e-skills-check',str(path)],capture_output=True,text=True)
  assert (p.returncode==0)==good,(p.stdout,p.stderr);return p.stdout
 assert 'reach start=2 hold=15 planar=1' in native(valid,True)
 assert 'reach start=0 hold=0 planar=0' in native(skills.cook(dict(config,reach=dict(start=0,hold=0,plane='3d'))),True)
 for cut in (0,3,12,len(valid)-1):native(valid[:cut],False)
 native(valid+b'\0',False)
 # The pre-PQ-465 layout (N3K1, no reach) is refused.
 native(b'N3K1'+valid[4:],False)
 for key,value in [('cast_ms',0),('cast_ms',10001),('amount',5001),('range',float('nan')),('range',51),('target',3),('class','demo:class/other'),('cast_joints',[12,12]),('target_joint',128)]:
  v=copy.deepcopy(config);v['skills'][0][key]=value
  try:skills.cook(v)
  except ValueError:pass
  else:raise AssertionError(('bad skill accepted',key,value))
 # Hostile reaches: the cooker and the native reader refuse the same ones.
 head=len(valid[:4])+4+len(config['archetype'])+4+len(config['label'])
 for start,hold,plane in [(-1,15,'xz'),(2,51,'xz'),(float('nan'),15,'xz'),(2,15,'yz'),(True,15,'xz')]:
  try:skills.cook(dict(config,reach=dict(start=start,hold=hold,plane=plane)))
  except ValueError:pass
  else:raise AssertionError(('bad skill reach accepted',start,hold,plane))
 for block in (f([-1,15])+u(1),f([2,51])+u(1),f([float('nan'),15])+u(1),f([2,15])+u(2)):
  native(valid[:head]+block+valid[head+12:],False)
 try:skills.cook({k:v for k,v in config.items() if k!='reach'})
 except ValueError:pass
 else:raise AssertionError('a policy without a reach was accepted')
 # PQ-466 (D-234): N3K3 adds the client's too-far notice after the reach; a
 # policy without one stays N3K2. One %s takes the skill's label.
 assert valid[:4]==b'N3K2' and "notice=''" in native(valid,True)
 for text in ('Skill Failed - Too far','%s is too far','x'*96):
  data=skills.cook(dict(config,notice=text));assert data[:4]==b'N3K3' and data[4:head]==valid[4:head]
  out=native(data,True);assert f"notice='{text}'" in out,out
 assert "formatted='Heal is too far'" in native(skills.cook(dict(config,notice='%s is too far')),True)
 for text in ('','%d too far','%s and %s','100%','%','tab\there','caf\u00e9','x'*97,None,5):
  try:skills.cook(dict(config,notice=text))
  except ValueError:pass
  else:raise AssertionError(('bad skill notice accepted',text))
  # The C++ reader refuses each string notice too, the empty one (length 0)
  # and the UTF-8 bytes of the non-ASCII one included (the same splice with a
  # good notice loads, below).
  if type(text) is str:
   data=text.encode('utf-8');bad=valid[:head+12]+u(len(data))+data+valid[head+12:]
   native(b'N3K3'+bad[4:],False)
 spliced=valid[:head+12]+u(7)+b'Too far'+valid[head+12:]
 assert "notice='Too far'" in native(b'N3K3'+spliced[4:],True)
 good=skills.cook(dict(config,notice='Too far'))
 native(b'N3K2'+good[4:],False);native(b'N3K3'+valid[4:],False)
 for cut in (head+12,head+16,head+18):native(good[:cut],False)
 # PQ-469 (D-235): N3K4 adds, after the notice, the client's line for the
 # server's out_of_range refusal and its colour (ARGB, alpha not 0); a failed
 # line needs a notice. One %s takes the skill's label.
 assert "failed='' color=00000000" in native(good,True)
 noticed=len(good[:head+12])+4+len('Too far')
 for text,color in (('%s failed',0xffff3b3b),('Failed',0x01000000),('x'*96,0xffffffff)):
  data=skills.cook(dict(config,notice='Too far',failed=dict(text=text,color=color)))
  assert data[:4]==b'N3K4' and data[4:noticed]==good[4:noticed] and data[noticed:noticed+4+len(text)+4]==u(len(text))+text.encode()+u(color)
  out=native(data,True);assert f"failed='{text}' color={color:08x}" in out,out
 assert "failed_formatted='Heal failed'" in native(skills.cook(dict(config,notice='Too far',failed=dict(text='%s failed',color=0xffff3b3b))),True)
 for value in (dict(text='',color=0xffff3b3b),dict(text='%d failed',color=0xffff3b3b),dict(text='%s and %s',color=0xffff3b3b),
               dict(text='caf\u00e9',color=0xffff3b3b),dict(text='x'*97,color=0xffff3b3b),dict(text='%s failed',color=0x00ff3b3b),
               dict(text='%s failed',color=1<<32),dict(text='%s failed',color=True),dict(text='%s failed'),dict(text='%s failed',color=0xffff3b3b,x=1),'%s failed'):
  try:skills.cook(dict(config,notice='Too far',failed=value))
  except ValueError:pass
  else:raise AssertionError(('bad skill failed line accepted',value))
  # The C++ reader refuses each bad string or colour too.
  if type(value) is dict and type(value.get('text')) is str and type(value.get('color')) is int and value['color']<1<<32 and 'x' not in value:
   data=value['text'].encode('utf-8');native(b'N3K4'+good[4:noticed]+u(len(data))+data+u(value['color'])+good[noticed:],False)
 try:skills.cook(dict(config,failed=dict(text='%s failed',color=0xffff3b3b)))
 except ValueError:pass
 else:raise AssertionError('a failed line without a notice was accepted')
 four=skills.cook(dict(config,notice='Too far',failed=dict(text='%s failed',color=0xffff3b3b)))
 native(b'N3K3'+four[4:],False);native(b'N3K4'+good[4:],False)
 for cut in (noticed,noticed+4,noticed+4+9,noticed+4+9+3):native(four[:cut],False)
 # PQ-479 (D-243): N3K5 adds, after the failed line, the client's lines for
 # the server's refusals at the acceptance: 1-8, one per status (not
 # out_of_range), each for any target, a player or an NPC, bounded as the
 # notice is, with a colour whose alpha is not 0.
 failed_line=dict(text='%s failed',color=0xffff3b3b)
 lines=[dict(status='level_required',target='any',text='Casting failed',color=0xffff3b3b),
        dict(status='insufficient_resource',target='any',text='Skill Failed - Not enough MP',color=0xffffff00),
        dict(status='target_dead',target='npc',text='Casting failed',color=0xffff3b3b),
        dict(status='wrong_class',target='player',text='%s: wrong class',color=0xffffff00)]
 five=skills.cook(dict(config,notice='Too far',failed=failed_line,refusals=lines))
 tail=len(u(len('Too far'))+b'Too far'+u(len('%s failed'))+b'%s failed'+u(0xffff3b3b))
 cut=head+12+tail
 assert five[:4]==b'N3K5' and five[4:cut]==four[4:cut] and five[cut:cut+4]==u(len(lines))
 out=native(five,True)
 for l in lines:
  want=f"refusal status={l['status']} target={['any','player','npc'].index(l['target'])} text='{l['text']}' color={l['color']:08x}"
  assert want in out,(want,out)
 assert 'refusal ' not in native(four,True)
 one=lambda status='level_required',target='any',text='Casting failed',color=0xffff3b3b:dict(status=status,target=target,text=text,color=color)
 for bad in ([],[one(s) for s in 'abcdefghi'],[one('out_of_range')],[one(),one(target='npc')],[one(target='self')],[one('Level')],
             [one('_level')],[one('')],[one('a'*33)],[one(text='')],[one(text='%d')],[one(text='caf\u00e9')],[one(color=0x00ffffff)],
             [one(color=1<<32)],[dict(one(),x=1)],[{k:v for k,v in one().items() if k!='target'}],'level_required',[one(status=5)]):
  try:skills.cook(dict(config,notice='Too far',failed=failed_line,refusals=bad))
  except ValueError:pass
  else:raise AssertionError(('bad skill refusal lines accepted',bad))
 assert skills.cook(dict(config,notice='Too far',failed=failed_line,refusals=[one(s) for s in 'abcdefgh']))[:4]==b'N3K5'
 try:skills.cook(dict(config,notice='Too far',refusals=lines))
 except ValueError:pass
 else:raise AssertionError('refusal lines without a failed line were accepted')
 # The C++ reader refuses the same hostile lines: splice raw blocks after the
 # failed line (the cooker would refuse to write them).
 def block(items,count=None):
  out=u(len(items) if count is None else count)
  for status,target,text,color in items:
   out+=u(len(status.encode()))+status.encode()+u(target)+u(len(text.encode()))+text.encode()+u(color)
  return out
 body=four[cut:]
 assert 'refusal status=a target=2' in native(b'N3K5'+four[4:cut]+block([('a',2,'x',0xff000000)])+body,True)
 for items,count in [([],None),([('a',0,'x',0xff000000)]*1+[(c,0,'x',0xff000000) for c in 'bcdefghi'],None),
                     ([('out_of_range',0,'x',0xff000000)],None),([('a',0,'x',0xff000000),('a',1,'y',0xff000000)],None),
                     ([('a',3,'x',0xff000000)],None),([('Level',0,'x',0xff000000)],None),([('_a',0,'x',0xff000000)],None),
                     ([('',0,'x',0xff000000)],None),([('a'*33,0,'x',0xff000000)],None),([('a',0,'',0xff000000)],None),
                     ([('a',0,'%d',0xff000000)],None),([('a',0,'caf\u00e9',0xff000000)],None),([('a',0,'x',0x00ffffff)],None),
                     ([('a',0,'x',0xff000000)],2)]:
  native(b'N3K5'+four[4:cut]+block(items,count)+body,False)
 native(b'N3K5'+four[4:],False);native(b'N3K4'+five[4:],False)
 for at in (cut,cut+4,cut+8,len(five)-len(body)-1):native(five[:at],False)
 # Both floats are the encoded range: reject nonfinite content at runtime too.
 native(valid.replace(struct.pack('<f',25),struct.pack('<f',float('nan'))),False)
 # Verify stereo unsigned PCM conversion and strict truncated WAV rejection.
 stream=io.BytesIO()
 with wave.open(stream,'wb')as w:w.setparams((2,1,24000,0,'NONE',''));w.writeframes(bytes([0,255,128,128])*8)
 decoded=ko_audio.pcm(stream.getvalue());assert len(decoded)==16*2*2 and max(struct.unpack('<'+'h'*(len(decoded)//2),decoded))==0
 try:ko_audio.pcm(stream.getvalue()[:-1])
 except ValueError:pass
 else:raise AssertionError('truncated PCM accepted')
 # PQ-013: N3A2 positional policy, cooker and native reader agree on bounds.
 audio=pathlib.Path(root)/'audio.bin'
 body=u(48000)+u(1)+u(1)+u(2)+b'\0\0\0\0'+u(0)+u(0)
 def load(data,good):
  audio.write_bytes(data);p=subprocess.run(['build/client/n3e-audio-check',str(audio)],capture_output=True,text=True)
  assert (p.returncode==0)==good,(data[:4],p.stdout,p.stderr);return p.stdout
 assert 'listener=0 effect=0 option=0-0 cutoff=30 reference=2' in load(b'N3AU'+body,True)
 ko=json.loads(pathlib.Path('games/moradon/audio.json').read_text());block=audio_spatial.cook(ko)
 assert 'listener=1 effect=48 option=20-48 cutoff=30 reference=2' in load(b'N3A2'+body+block,True)
 off=dict(ko,effect_distance=0,effect_distance_min=0,effect_distance_max=0,listener='camera')
 assert 'listener=0 effect=0 option=0-0' in load(b'N3A2'+body+audio_spatial.cook(off),True)
 for data in (b'N3A2'+body,b'N3AU'+body+block,b'N3A2'+body+block[:-1],b'N3A2'+body+block+b'\0',b'N3A3'+body+block):load(data,False)
 # Hostile blocks the cooker refuses must fail natively too.
 for listener,values in [(2,[48,20,48,30,2]),(1,[49,20,48,30,2]),(1,[19,20,48,30,2]),(1,[48,20,48,float('nan'),2]),(1,[48,20,48,30,30]),(1,[0,20,48,30,2]),(1,[48,20,48,4,2]),(1,[48,0.5,48,30,2])]:
  load(b'N3A2'+body+u(listener)+f(values),False)
  try:audio_spatial.cook(dict(zip(audio_spatial.FIELDS,[(audio_spatial.LISTENERS+['x'])[min(listener,2)]]+values)))
  except ValueError:pass
  else:raise AssertionError(('bad audio spatial accepted',listener,values))
 for bad in (dict(ko,extra=1),{k:v for k,v in ko.items() if k!='cutoff'},dict(ko,reference=True)):
  try:audio_spatial.cook(bad)
  except ValueError:pass
  else:raise AssertionError(('bad audio spatial accepted',bad))
print('PASS skill cooker/C++ compatibility (N3K2, N3K3 notice, N3K4 failed line, N3K5 refusal lines), hostile bounds, audio PCM conversion/truncation and N3A2 positional policy')
