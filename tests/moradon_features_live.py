"""Exercise the integrated local Moradon release with separate disposable audit accounts.
Run tools/play-moradon --provision-only first. No user character data is modified.
"""
import json,os,secrets,select,subprocess,time,uuid
from pathlib import Path
from world_peer import Peer,first,fields,integer,blob
import moradon_stack
from moradon_route import to_worms,to_start
state=moradon_stack.state()
package=moradon_stack.PACKAGE;m=json.loads((package/'recipe.json').read_text())['manifest']
assert m['engine_version']>=36 and m['npc']['model']=='reference_melee_v2'
assert (package/'release.sha256').read_text().strip()==state['release']
env={**os.environ,'N3E_PACKAGE_PATH':str(package.resolve()),'N3E_REALM':state['realm'],'N3E_PORT':str(state['port']),'N3E_IMAGE':moradon_stack.IMAGE}
compose=['docker','compose','-p',moradon_stack.PROJECT]
def run(*cmd,input=None):return subprocess.run(cmd,input=input,env=env,text=True,capture_output=True,check=True).stdout
suffix=uuid.uuid4().hex[:7];peers=[];accounts=[];names=['AuditA'+suffix,'AuditB'+suffix];last_ping=0;serial=0
for n in names:
 password=secrets.token_urlsafe(24);account=n.lower()
 run(*compose,'exec','-T','server','n3e-server','account-create',account,input=password+'\n')
 run(*compose,'exec','-T','server','n3e-server','storage-password-init',account,input='Moradon1\n')
 accounts.append((account,password))
 p=Peer(state['port'],account,password,content=state['release'],game=m['game_id'],protocol=m['protocol_version'])
 p.select(p.create(n));peers.append(p)
a,b=peers

def wait(p,tag,predicate=lambda d:True,timeout=8):
 global last_ping
 deadline=time.monotonic()+timeout
 while time.monotonic()<deadline:
  if time.monotonic()-last_ping>.5:
   for peer in peers:peer.send(14)
   last_ping=time.monotonic()
  t,d=p.receive();assert t!=4,(t,d)
  if t==tag and predicate(d):return d
 raise AssertionError(('timeout',tag))
def request(p,tag,data,reply,status=None):
 time.sleep(.22) # Stay inside the shared inventory/auth request budget.
 p.send(tag,data);d=wait(p,reply)
 if status:assert first(d,2)==status,(tag,d,status)
 return d
def name():
 global serial
 serial+=1;return 'moradon-'+suffix+'-'+str(serial)
def bag(p):return fields(first(request(p,32,b'',33,b'ok'),3))
def bagop(p,s,op,src=0,dst=0,item='',qty=0):
 records=s[6]if op in (6,7,8)else s[5]
 q=integer(1,op)+blob(2,name())+integer(3,first(s,1))+integer(4,src)+integer(5,dst)+integer(6,first(fields(records[src]),1))+blob(8,item)+integer(9,qty)
 if op in (2,3):q+=blob(7,m['commerce']['shops'][0]['id'])
 return fields(first(request(p,32,q,33,b'committed'),3))
def party(p,op=0,target='',token=0):
 return request(p,42,integer(1,serial+100)+integer(2,op)+blob(3,target)+integer(4,token),44)
def drain(p):
 # Consume every already-received message so decisions use the latest snapshot.
 while p.s.pending() or select.select([p.s],[],[],0)[0]:
  t,d=p.receive();assert t!=4,(t,d)
def acknowledged(p):
 # The server admits one movement per tick; send the next only after it acknowledged the last.
 return first(p.entities[p.id],6)>=p.seq
def walk(p,x,z,tolerance=.7):
 # Long route legs are allowed time in proportion to distance.
 here=p.entities[p.id];deadline=time.monotonic()+30+((x-first(here,3))**2+(z-first(here,5))**2)**.5/1.5
 while time.monotonic()<deadline:
  wait(p,10);drain(p);me=p.entities[p.id]
  if not acknowledged(p):continue
  dx=x-first(me,3);dz=z-first(me,5);d=(dx*dx+dz*dz)**.5
  if d<tolerance:p.move(0,0);return
  p.move(dx/max(1,d),dz/max(1,d),mode=1)
 raise AssertionError(('Moradon route blocked',p.id,x,z,p.entities[p.id]))
def walk_all(x,z):
 # Long routes move every peer each tick so no socket stops draining; the server
 # drops input from a client whose bounded outbound queue is not read.
 here=[p.entities[p.id] for p in peers];deadline=time.monotonic()+30+max(((x-first(e,3))**2+(z-first(e,5))**2)**.5 for e in here)/1.5
 done=set()
 while time.monotonic()<deadline and len(done)<len(peers):
  for p in peers:
   wait(p,10);drain(p)
   if p.id in done or not acknowledged(p):continue
   me=p.entities[p.id];dx=x-first(me,3);dz=z-first(me,5);d=(dx*dx+dz*dz)**.5
   if d<.7:p.move(0,0);done.add(p.id);continue
   p.move(dx/max(1,d),dz/max(1,d),mode=1)
  time.sleep(.02)
 if len(done)<len(peers):raise AssertionError(('Moradon route blocked',x,z,[p.entities[p.id] for p in peers]))
try:
 sx,sz=m['gameplay']['spawn_x'],m['gameplay']['spawn_z']
 for p in peers:
  me=p.entities[p.id];assert abs(first(me,3)-sx)<.01 and abs(first(me,5)-sz)<.01
 # New accounts are ordinary; no tool build or demo mode grants turbo implicitly.
 assert not first(wait(a,10),11)
 a.send(31,blob(1,names[1])+blob(2,'Moradon private message'))
 whisper=wait(b,11);assert first(whisper,1)==b'Moradon private message' and first(whisper,4)==1
 roster=request(a,38,b'',39,b'ok')
 request(a,38,integer(1,1)+blob(2,name())+integer(3,first(roster,3))+blob(4,names[1]),39,b'committed')
 presence=request(a,40,integer(1,1)+blob(2,names[1]),41)
 assert first(fields(presence[3][0]),4)==1
 s=bag(a);coins=first(s,4)
 s=bagop(a,s,2,9,item='demo:item/potion',qty=1)
 assert first(s,4)==coins-13
 s=bagop(a,s,3,9,item='demo:item/potion',qty=1)
 assert first(s,4)==coins-11
 for src,dst in [(0,0),(2,1),(4,2)]:s=bagop(a,s,5,src,dst)
 assert first(fields(s[6][0]),2)==b'demo:item/blade'
 def appearance(observer,expected):
  wait(observer,10,lambda _:list(first(observer.entities.get(a.id,{}),20,b''))==expected)
  style=4 if 4 in expected else 3 if 1 in expected and 2 in expected else 2 if 1 in expected else 5 if 3 in expected else 1
  wait(observer,10,lambda _:first(observer.entities.get(a.id,{}),22)==style)
 appearance(a,[1,3]);appearance(b,[1,3])
 s=bagop(a,s,5,8,4);appearance(b,[1,3,5]);appearance(a,[1,3,5])
 # An occupied two-hand exclusion rejects; after freeing the main hand it
 # displaces the shield atomically and snapshots expose only the new keys.
 s=bagop(a,s,6,0,0);appearance(b,[3,5])
 s=bagop(a,s,5,3,0);appearance(b,[4,5])
 s=bagop(a,s,6,0,2);appearance(b,[5])
 s=bagop(a,s,5,0,0);s=bagop(a,s,5,3,1);appearance(b,[1,3,5])
 # Reconnect verifies that public appearance derives from committed gear.
 a.logout();peers.remove(a)
 a=Peer(state['port'],accounts[0][0],accounts[0][1],content=state['release'],game=m['game_id'],protocol=m['protocol_version']);a.select(a.characters[0][0]);peers.insert(0,a)
 appearance(a,[1,3,5]);appearance(b,[1,3,5])
 assert bag(a)==s
 service=m['storage']['services'][0]['id']
 request(a,34,blob(2,name())+integer(3,first(s,1))+blob(5,service),35,b'locked')
 auth=request(a,36,integer(1,1)+blob(2,name())+blob(3,service)+blob(4,'Moradon1'),37)
 assert first(auth,4)>0,auth
 opened=request(a,34,blob(2,name())+integer(3,first(s,1))+blob(5,service),35,b'committed');bank=fields(first(opened,4));s=fields(first(opened,3))
 def bankop(op,src=0,dst=0,qty=0):
  global s,bank
  records=s[5]if op==1 else bank[4]
  instance=first(fields(records[src]),1)if op in(1,2,3)else 0
  q=integer(1,op)+blob(2,name())+integer(3,first(s,1))+integer(4,first(bank,1))+blob(5,service)+integer(6,src)+integer(7,dst)+integer(8,instance)+integer(9,qty)
  d=request(a,34,q,35,b'committed');s=fields(first(d,3));bank=fields(first(d,4));return d
 instance=first(fields(s[5][5]),1)
 bankop(1,5,0,1);assert first(fields(bank[4][0]),1)==instance
 bankop(2,0,5,1);assert first(fields(s[5][5]),1)==instance
 before=first(s,4);bankop(4,qty=20);bankop(5,qty=20);assert first(s,4)==before
 assert first(party(a,1,names[1]),2)==b'invited'
 invite=wait(b,43,lambda d:first(d,5)>0)
 assert first(party(b,2,token=first(invite,5)),2)==b'joined'
 old_xp=[first(p.inventory,4)for p in peers]
 # Follow the build-verified route from the town square to the reference worm area.
 walk_all(sx,sz);to_worms(walk_all)
 deadline=time.monotonic()+40
 while time.monotonic()<deadline:
  wait(a,10);wait(b,10)
  if first(a.inventory,4)>old_xp[0]:break
  targets=[e for e in a.entities.values()if first(e,9)and first(e,7)]
  if targets:
   target=min(targets,key=lambda e:(first(e,3)-first(a.entities[a.id],3))**2+(first(e,5)-first(a.entities[a.id],5))**2)
   # Passive reference worms do not approach; the attacker closes the distance.
   if (first(target,3)-first(a.entities[a.id],3))**2+(first(target,5)-first(a.entities[a.id],5))**2>1:walk(a,first(target,3)-.6,first(target,5),.3)
   a.action(first(target,1))
  time.sleep(.15)
 else:raise AssertionError('No durable worm settlement')
 wait(b,10,lambda _:first(b.inventory,4)>old_xp[1])
 assert first(b.inventory,4)>old_xp[1],(b.inventory,old_xp)
 a.send(23);drops=[fields(v)for v in wait(a,24).get(1,[])]
 # Passive worms fall to one blade hit, so a second kill can land before the first settles.
 assert len(drops)>=3 and len(drops)%3==0,drops
 balances=[first(bag(p),4)for p in peers]
 for d in sorted(drops,key=lambda d:first(d,10)):
  walk(a,first(d,5),first(d,7))
  serial+=1
  result=request(a,25,integer(1,a.session)+integer(2,serial)+integer(3,a.id)+integer(4,first(d,1))+integer(5,first(d,2))+blob(6,first(d,3))+integer(7,first(d,9)),26)
  if first(result,2)==b'pending':result=wait(a,26,lambda r:first(r,1)==first(d,1)and first(r,2)!=b'pending')
  assert first(result,2)==b'claimed',result
  a.send(27,integer(1,first(d,1)));assert wait(a,26)==result
 assert all(first(bag(p),4)>value for p,value in zip(peers,balances))
 s=bag(a);blade=fields(s[6][0]);assert first(blade,4)<80,blade
 # Reference worms are passive and fall to one blade hit; unarmed hits draw real retaliation.
 s=bag(a);spare=next(i for i,v in enumerate(s[5])if not fields(v))
 s=bagop(a,s,6,0,spare);maximum=first(wait(a,10),8);deadline=time.monotonic()+60
 while first(a.entities[a.id],7)>=maximum and time.monotonic()<deadline:
  wait(a,10);wait(b,10);targets=[e for e in a.entities.values()if first(e,9)and first(e,7)]
  if targets:
   target=min(targets,key=lambda e:(first(e,3)-first(a.entities[a.id],3))**2+(first(e,5)-first(a.entities[a.id],5))**2)
   if (first(target,3)-first(a.entities[a.id],3))**2+(first(target,5)-first(a.entities[a.id],5))**2>1:walk(a,first(target,3)-.6,first(target,5),.3)
   a.action(first(target,1))
  time.sleep(.15)
 assert first(a.entities[a.id],7)<maximum,'no worm retaliation'
 # Retaliation wears armour, which advances the bag revision.
 s=bagop(a,bag(a),5,spare,0)
 # The later style checks need the latest accepted strike to be armed again.
 deadline=time.monotonic()+30;armed=False
 while not armed and time.monotonic()<deadline:
  wait(a,10);wait(b,10);targets=[e for e in a.entities.values()if first(e,9)and first(e,7)]
  if targets:
   target=min(targets,key=lambda e:(first(e,3)-first(a.entities[a.id],3))**2+(first(e,5)-first(a.entities[a.id],5))**2)
   if (first(target,3)-first(a.entities[a.id],3))**2+(first(target,5)-first(a.entities[a.id],5))**2>1:walk(a,first(target,3)-.6,first(target,5),.3)
   armed=a.action(first(target,1)) in ('hit','miss')
  time.sleep(.15)
 assert armed,'no armed strike after re-equipping'
 to_start(walk_all,(sx,sz))
 s=bag(a);s=bagop(a,s,8,0,item='demo:item/blade');assert first(fields(s[6][0]),4)==80
 # Changing equipped style must not rewrite the style of the accepted strike.
 wait(b,10,lambda _:first(b.entities.get(a.id,{}),23)==2)
 s=bagop(a,s,6,0,9);appearance(a,[3,5]);appearance(b,[3,5])
 assert first(a.entities[a.id],23)==2 and first(b.entities[a.id],23)==2
 s=bagop(a,s,5,9,0);appearance(a,[1,3,5]);appearance(b,[1,3,5])
 print('PASS public equipped combat profiles, remote agreement and strike style frozen across unequip')
 # Real damage is required: do not fake health or write user state.
 assert first(a.entities[a.id],7)<first(wait(a,10),8)
 rest_seq=1
 def rest(sitting,seq=None,entity=None):
  global rest_seq
  q=integer(1,a.session)+integer(2,rest_seq if seq is None else seq)+integer(3,a.id if entity is None else entity)+integer(4,int(sitting))
  if seq is None:rest_seq+=1
  a.send(45,q);return q
 # Moving has stopped before admission. Invalid identities never set posture.
 time.sleep(.25);rest(True,entity=b.id)
 assert first(a.until(4)[1],2)==b'stale_rest_identity'
 q=rest(True);start=wait(a,10,lambda _:first(a.entities[a.id],21)==1)
 hp=first(a.entities[a.id],7);tick=first(start,1)
 wait(b,10,lambda _:first(b.entities.get(a.id,{}),21)==1)
 a.send(45,q);assert first(a.until(4)[1],2)==b'stale_rest_sequence'
 # Tick-based recovery cannot be accelerated by messages; resource is clamped.
 snap=wait(a,10,lambda d:first(d,1)>=tick+104,timeout=9)
 assert first(a.entities[a.id],7)>hp and first(a.entities[a.id],7)<=first(snap,8)
 assert first(a.entities[a.id],8)<=first(snap,9)
 rest(False);wait(a,10,lambda _:not first(a.entities[a.id],21))
 rest(True);wait(a,10,lambda _:first(a.entities[a.id],21)==1)
 a.move(1,0);wait(a,10,lambda _:not first(a.entities[a.id],21));a.move(0,0)
 print('PASS Moradon rest identity/sequence authority, remote sitting, timed health/resource recovery, stand and movement cancellation')
 saved=[bag(p)for p in peers]
 for p in peers:p.logout()
 peers.clear()
 for (account,password),expected in zip(accounts,saved):
  p=Peer(state['port'],account,password,content=state['release'],game=m['game_id'],protocol=m['protocol_version']);p.select(p.characters[0][0]);peers.append(p)
  assert bag(p)==expected
 print('PASS Moradon public appearance equip/displace/clear/reconnect and remote snapshots, configured spawn, whisper, friends/presence, buy/sell, equipment, protected storage item/coin transfers, real KO worm combat/wear/repair, party XP/item/coins, retry and reconnect conservation')
finally:
 for p in peers:
  try:p.logout()
  except (OSError,EOFError):p.s.close()
