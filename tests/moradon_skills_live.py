"""Starter skills through real TLS, ordinary progression and durable cooldowns.

PQ-466 (D-234): with N3E_GRAPHICAL=1 the real client, at level 2, selects a
worm beyond Light Strike's start limit and uses it: it posts the package's
too-far notice (the player's text 4009) and sends nothing. PQ-469 (D-235):
it then uses it again without the client's hint; the server refuses it
out_of_range and the client draws the player's text 4004 ("%s failed"),
formatted with the skill's label, in 1298's red 0xffff3b3b.
"""
import json, os, secrets, subprocess, time
from pathlib import Path
from world_peer import Peer, fields, first, integer, blob
import moradon_stack
from moradon_route import to_worms, walker, worm_areas
state=moradon_stack.state()
package=moradon_stack.PACKAGE;m=json.loads((package/'recipe.json').read_text())['manifest']
assert m['engine_version']>=36 and m['npc']['model']=='reference_melee_v2' and state['release']==(package/'release.sha256').read_text().strip()
env={**os.environ,'N3E_IMAGE':moradon_stack.IMAGE,'N3E_PACKAGE_PATH':str(package.resolve()),'N3E_PORT':str(state['port']),'N3E_REALM':state['realm']}
account='skills'+secrets.token_hex(5);password=secrets.token_urlsafe(24)
subprocess.run(['docker','compose','-p',moradon_stack.PROJECT,'exec','-T','server','n3e-server','account-create',account],input=password+'\n',env=env,text=True,capture_output=True,check=True)
def connect():return Peer(state['port'],account,password,content=state['release'],game=m['game_id'],protocol=m['protocol_version'])
p=connect();character=p.create('Skill'+secrets.token_hex(3));p.select(character);p.pump(.5)
heal,strike=[s['id'] for s in m['skills']['skills']]
def self():return p.entities[p.id]
def final(seq,timeout=8):
 end=time.monotonic()+timeout;ping=0
 while time.monotonic()<end:
  if time.monotonic()>=ping:p.send(14);ping=time.monotonic()+.5
  t,d=p.receive();assert t!=4,(t,d)
  if t==16 and first(d,1)==seq and first(d,2) not in (b'cast_pending',b'casting'):return d
 raise AssertionError('skill result timeout')
def cast(skill,target,expected):
 p.action_seq+=1;p.send(15,integer(1,p.session)+integer(2,p.action_seq)+integer(3,target)+blob(4,skill))
 r=final(p.action_seq);assert first(r,2) in tuple(x.encode() for x in (expected if isinstance(expected,tuple)else (expected,))),(r,self(),p.entities);p.pump(.1);return r

def walk(x,z):walker(p,first,.25)(x,z)
def npc():return min((e for e in p.entities.values() if first(e,9) and first(e,7)),key=lambda e:(first(e,3)-first(self(),3))**2+(first(e,5)-first(self(),5))**2)
def bag():p.send(32);return fields(first(p.until(33)[1],3))
def drink():
 s=bag();slot=next(i for i,v in enumerate(s[5])if first(fields(v),2)==b'demo:item/potion')
 request='skill-drink-'+secrets.token_hex(4)
 p.send(32,integer(1,9)+blob(2,request)+integer(3,first(s,1))+integer(4,slot)+integer(6,first(fields(s[5][slot]),1)))
 end=time.monotonic()+3;ping=0
 while time.monotonic()<end:
  if time.monotonic()>=ping:p.send(14);ping=time.monotonic()+.5
  t,r=p.receive()
  if t==33 and first(r,1)==request.encode() and first(r,2)!=b'use_pending':assert first(r,2)==b'consumed',r;return
 raise AssertionError('potion recovery timeout')
def alive(target):return first(p.entities.get(target,{}),7)>0
def other(target):
 # Another live worm for gate checks after a 7 HP reference worm dies to one spell.
 return first(min((e for e in p.entities.values() if first(e,9) and first(e,7) and first(e,1)!=target),key=lambda e:(first(e,3)-first(self(),3))**2+(first(e,5)-first(self(),5))**2),1)
try:
 # Reference worms live outside the town walls and are passive (N3N2).
 to_worms(walk);p.pump(.5)
 cast(strike,first(npc(),1),'level_required')
 cast(heal,first(npc(),1),'invalid_target')
 resource=first(self(),8)
 # Movement cancels an admitted cast before MP or healing is committed.
 assert p.action(p.id,action=heal)=='cast_pending'
 end=time.monotonic()+3
 while not first(self(),26,b'') and time.monotonic()<end:p.pump(.05)
 assert first(self(),26)==heal.encode()
 p.move(.5,0);assert first(final(p.action_seq),2)==b'interrupted';p.move(0,0);p.pump(.2)
 assert first(self(),8)==resource
 # Existing sequence is never allowed to apply again.
 assert p.action(p.id,seq=p.action_seq,action=heal)=='stale_action'
 # Earn level 2 through the existing weapon/death/reward pipeline.
 s=bag();p.send(32,integer(1,5)+blob(2,'skills-equip')+integer(3,first(s,1))+integer(4,0)+integer(6,first(fields(s[5][0]),1)))
 assert first(p.until(33)[1],2)==b'committed'
 for _ in range(3):
  if first(p.inventory,5)>=2:break
  e=npc();target=first(e,1);walk(first(e,3)-.3,first(e,5));end=time.monotonic()+35
  while target in p.entities and first(p.entities[target],7)>0 and time.monotonic()<end:
   result=p.action(target);assert result in ('hit','miss','cooldown','combat_pending','target_pending'),result;p.pump(.15)
  assert target not in p.entities or first(p.entities[target],7)==0
  p.pump(.6)
 assert first(p.inventory,5)>=2,p.inventory
 # One blade hit kills a 7 HP reference worm, so unequip and let one retaliate for real damage.
 s=bag();p.send(32,integer(1,6)+blob(2,'skills-unarm')+integer(3,first(s,1))+integer(5,9)+integer(6,first(fields(s[6][0]),1)))
 assert first(p.until(33)[1],2)==b'committed'
 p.send(14);_,w=p.until(10);maximum=first(w,8);end=time.monotonic()+60;e=None
 while (first(self(),7)>=maximum or (e and alive(first(e,1)))) and time.monotonic()<end:
  if e is None or not alive(first(e,1)):e=npc();walk(first(e,3)-.3,first(e,5))
  p.action(first(e,1));p.pump(.15)
 p.pump(.5)
 hp=first(self(),7);mp=first(self(),8);assert hp<maximum
 cast(heal,p.id,'healed');assert first(self(),7)==min(maximum,hp+15) and mp-5<=first(self(),8)<=mp-2,(self(),hp,mp)
 p.pump(.4)
 target=first(npc(),1);before=first(p.entities[target],7);mp=first(self(),8)
 r=cast(strike,target,'hit');damage=first(r,4);assert 1<=damage<=100
 assert first(p.entities.get(target,{}),7)==max(0,before-damage) and mp-5<=first(self(),8)<=mp-2,(target,before,damage,p.entities,mp)
 if not alive(target):target=other(target)
 cast(strike,target,'cooldown')
 # A reconnect must recover both server admission and the displayed recast gate.
 p.logout();p=connect();p.select(character);p.pump(.3)
 p.send(14);_,world=p.until(10)
 assert any(first(fields(x),1)==strike.encode() for x in world.get(16,[])),world.get(16)
 if not alive(target):target=other(target)
 cast(strike,target,'cooldown')
 p.pump(5.5)
 if target not in p.entities or not first(p.entities[target],7):target=first(npc(),1)
 # Lower a target with ordinary unarmed attacks, then deliver the killing spell.
 # This checks mixed contribution credit and the spell death/reward path without
 # depending on surviving a long series of intentionally interruptible casts.
 e=p.entities[target];walk(first(e,3)-.3,first(e,5));end=time.monotonic()+70
 while first(p.entities.get(target,{}),7)>6 and time.monotonic()<end:
  if first(self(),7)<maximum-70:drink()
  result=p.action(target);assert result in ('hit','miss','cooldown','combat_pending','target_pending'),result;p.pump(.15)
 assert 0<first(p.entities.get(target,{}),7)<=6,p.entities
 start_xp=first(p.inventory,4);end=time.monotonic()+20;p.pump(.3)
 while target in p.entities and first(p.entities[target],7)>0 and time.monotonic()<end:
  if first(self(),7)<maximum-70:drink()
  cast(strike,target,('hit','interrupted'));p.pump(.3)
 p.pump(.7);assert first(p.inventory,4)>start_xp,(p.inventory,start_xp)
 print('PASS TLS level/target gates, movement cancellation, no premature cost, stale sequence, exact healing/MP, magic damage, cooldown rejection/reconnect and spell kill rewards')
 if os.environ.get('N3E_GRAPHICAL')=='1':
  # PQ-466 (D-234): the real client, level 2 now, selects a worm beyond Light
  # Strike's start limit (25 + the melee radii 2 + the reach's start 2, in
  # 3-D) and uses the skill: it posts the package's too-far notice (the
  # player's text 4009) and sends nothing. Walk back along the worm route
  # until a visible worm lies 31-45 m away on the ground.
  import math,re
  def planar(e):return math.hypot(first(e,3)-first(self(),3),first(e,5)-first(self(),5))
  def far():
   band=[e for e in p.entities.values() if first(e,9) and first(e,7) and 31<=planar(e)<=45]
   return min(band,key=lambda e:abs(planar(e)-34)) if band else None
  w=far()
  for x,z in reversed(worm_areas()[0]['route'][:-1]):
   if w:break
   walk(x,z);p.pump(.5);w=far()
  assert w,('no worm 31-45 m away along the route',p.entities)
  worm=first(w,1);notice=m['skills']['notice'];limit=m['skills']['skills'][1]['range']+2+m['skills']['reach']['start']
  print(f'skill too-far worm {worm} at {planar(w):.2f} m (limit {limit} m)',flush=True)
  p.logout()
  work=Path('build/ko-completion/skills');work.mkdir(parents=True,exist_ok=True);capture=work/'too-far.ppm';capture.unlink(missing_ok=True)
  run=subprocess.run(['build/client/n3e-test-client',str(package.resolve()),'--connect','localhost:'+str(state['port']),'--ca','deploy/local/ca.pem',
                      '--auto-login','--fixed-window','1024x768','--world-smoke','7','--capture',str(capture)],
                     env={**os.environ,'N3E_TEST_ACCOUNT':account,'N3E_TEST_PASSWORD':password,'N3E_TEST_STAND_STILL':'1',
                          'N3E_TEST_SHOWCASE_SELECT':f'2.0 {worm}','N3E_TEST_SHOWCASE_SKILL':'3.0 1;4.5 1 unchecked'},
                     capture_output=True,text=True,timeout=180)
  text=run.stdout+run.stderr;(work/'too-far.log').write_text(text)
  assert run.returncode==0 and capture.stat().st_size>0,(run.returncode,text[-2000:])
  assert re.search(rf'^SHOWCASE_SELECT at=\S+ id={worm} seen=1$',text,re.M),text[-2000:]
  refused=re.findall(r"^SKILL_TOO_FAR skill=(\S+) target=(\d+) distance=(\S+) limit=(\S+) notice='(.*)'$",text,re.M)
  assert [(k,int(t),n) for k,t,_,_,n in refused]==[(strike,worm,notice.replace('%s',m['skills']['skills'][1]['label']))],(refused,text[-2000:])
  assert float(refused[0][3])==limit and float(refused[0][2])>limit,refused
  sent=re.findall(r'^SKILL_SENT skill=(\S+) target=(\d+) seq=(\d+)( unchecked)?$',text,re.M)
  assert sent==[(strike,str(worm),'1',' unchecked')],(sent,text[-2000:])
  # PQ-469 (D-235): the server refused the unchecked Light Strike out_of_range
  # (29 m in 3-D) and the client drew the player's text 4004 in 0xffff3b3b.
  failed=m['skills']['failed'];want=failed['text'].replace('%s',m['skills']['skills'][1]['label'])
  assert failed['color']==0xffff3b3b,failed
  got=re.findall(r"^SKILL_FAILED skill=(\S+) text='(.*)' color=([0-9a-f]{8})$",text,re.M)
  assert got==[(strike,want,'ffff3b3b')],(got,text[-2000:])
  drawn=re.findall(r"^SKILL_FAILED_DRAWN text='(.*)' color=([0-9a-f]{8})$",text,re.M)
  assert drawn==[(want,'ffff3b3b')],(drawn,text[-2000:])
  print(f"PASS Moradon skill server refusal graphical: Light Strike sent without the client's hint was refused "
        f"out_of_range and drew '{want}' in ffff3b3b",flush=True)
  print(f'PASS Moradon skill too far graphical: Light Strike on a worm at {float(refused[0][2]):.2f} m (limit {limit:g} m) '
        f"posted the package's notice '{refused[0][4]}' and sent nothing for that press; capture {capture}",flush=True)
 else:p.logout()
finally:p.s.close()
