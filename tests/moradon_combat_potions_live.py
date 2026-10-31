"""Real Moradon damage/moving-strike and recovery audit; disposable account only."""
import json,os,secrets,subprocess,time
from pathlib import Path
from world_peer import Peer,fields,first,integer,blob
import moradon_stack
from moradon_route import to_worms,walker
state=moradon_stack.state();package=moradon_stack.PACKAGE
m=json.loads((package/'recipe.json').read_text())['manifest'];assert m['engine_version']>=36 and m['npc']['model']=='reference_melee_v2'
# The package's potions share one lockout that starts when a drink commits
# (character_consumable_cooldowns, server/src/consumables.rs; 2000 ms in Moradon).
cooldown=max(c['cooldown_ms'] for c in m['consumables'])/1000
assert state['release']==(package/'release.sha256').read_text().strip()
env={**os.environ,'N3E_IMAGE':moradon_stack.IMAGE,'N3E_PACKAGE_PATH':str(package.resolve()),'N3E_PORT':str(state['port']),'N3E_REALM':state['realm']}
account='cp'+secrets.token_hex(6);password=secrets.token_urlsafe(24)
subprocess.run(['docker','compose','-p',moradon_stack.PROJECT,'exec','-T','server','n3e-server','account-create',account],input=password+'\n',env=env,text=True,capture_output=True,check=True)
def connect():return Peer(state['port'],account,password,content=state['release'],game=m['game_id'],protocol=m['protocol_version'])
p=connect();p.select(p.create('Cp'+secrets.token_hex(4)));sequence=0

def reply(tag,name=None):
 deadline=time.monotonic()+8
 while time.monotonic()<deadline:
  p.send(14);t,d=p.receive();assert t!=4,(t,d)
  if t==tag and (name is None or first(d,1,b'')==name):return d
 raise AssertionError(('missing reply',tag,name))
def bag():p.send(32);return fields(first(reply(33,b''),3))
def op(s,operation,source=1,item='',quantity=0):
 global sequence
 sequence+=1;name=('cp-'+str(sequence)).encode()
 q=integer(1,operation)+blob(2,name)+integer(3,first(s,1))+integer(4,source)+integer(6,first(fields(s[5][source]),1))+blob(8,item)+integer(9,quantity)
 if operation==2:q+=blob(7,m['commerce']['shops'][0]['id'])
 return q,name

def send(q,name,status):
 started=time.monotonic();p.send(32,q);r=reply(33,name);assert first(r,2)==status,r
 return r,fields(first(r,3)),time.monotonic()-started

walk=walker(p,first,.3)
def nearest(full=False):
 alive=[e for e in p.entities.values()if first(e,9)and first(e,7)and(not full or first(e,7)==m['gameplay']['npc_health'])]
 return min(alive,key=lambda e:(first(e,3)-first(p.entities[p.id],3))**2+(first(e,5)-first(p.entities[p.id],5))**2)if alive else None
def approach(npc):walk(first(npc,3)-.6,first(npc,5))
# Committed drinks reply after their commit, so cooldown seconds after the last
# reply the server's lockout has ended (PQ-428).
def rested():p.pump(max(0,drunk+cooldown+.1-time.monotonic()))
try:
 s=bag();q,name=op(s,2,9,'demo:item/mana_potion',1);_,s,_=send(q,name,b'committed')
 # Reference worms live outside the town walls and are passive (N3N2).
 to_worms(walk);p.pump(.5)
 maximum=first(reply(10),8);full=first(p.entities[p.id],7);start=first(p.inventory,5)
 npc=nearest();approach(npc)
 # An authenticated nonzero movement command is admitted before the attack.
 p.move(.2,0,mode=1);assert p.action(first(npc,1)) in ('hit','miss');p.pump(.15)
 assert first(p.entities[p.id],24)==1,p.entities[p.id]
 strike=first(p.entities[p.id],10);assert first(p.entities[p.id],23)==1
 assert p.action(first(npc,1))=='cooldown'
 p.move(0,0);p.pump(.1)
 # Unarmed damage leaves the worm alive long enough to retaliate: real NPC damage.
 deadline=time.monotonic()+40
 while first(p.entities[p.id],7)>=full and time.monotonic()<deadline:
  if npc is None or first(p.entities.get(first(npc,1),{}),7)==0:
   npc=nearest()
   if npc:approach(npc)
  if npc:p.action(first(npc,1))
  p.pump(.15)
 assert 0<first(p.entities[p.id],7)<full,'requires real NPC damage'
 # Finish the attacker so recovery below is not interrupted by further hits.
 deadline=time.monotonic()+20
 while npc and first(p.entities.get(first(npc,1),{}),7)>0 and time.monotonic()<deadline:p.action(first(npc,1));p.pump(.15)
 assert npc and first(p.entities.get(first(npc,1),{}),7)==0,('the attacker did not fall',npc)
 # PQ-409: each kill's settlement lands asynchronously and can raise the level, and
 # with it the maximum the potion is capped at. Settlements apply in kill order and
 # credit only their damage ledger (no party here), so once the last kill's encounter is the latest
 # settlement the level is stable; the maximum is then read from that same snapshot.
 deadline=time.monotonic()+20
 while first(p.inventory,11)!=first(npc,1):
  assert time.monotonic()<deadline,('the last kill never settled',first(npc,1),p.inventory);p.pump(.2)
 world=reply(10);maximum=first(world,8);level=first(p.inventory,5)
 hp=first(p.entities[p.id],7);mp=first(p.entities[p.id],8);assert hp<maximum,(hp,maximum,level)
 s=bag();q,name=op(s,9);result,s,elapsed=send(q,name,b'consumed');drunk=time.monotonic();assert elapsed>=.45
 p.pump(.15);world=reply(10);assert (first(world,8),first(p.inventory,5))==(maximum,level),(world,maximum,level)
 assert first(p.entities[p.id],7)==min(maximum,hp+90),(hp,p.entities[p.id],maximum,level)
 if level!=start:print(f'NOTE kills raised the level {start} -> {level} and the maximum health to {maximum} before the potion check',flush=True)
 qty=first(fields(s[5][1]),3);assert qty==4
 hp=first(p.entities[p.id],7);retry,same,_=send(q,name,b'consumed');assert retry==result
 p.pump(.15);assert first(p.entities[p.id],7)==hp and bag()==s
 qmp,nmp=op(s,9,9);_,same,_=send(qmp,nmp,b'cooldown');assert same==s
 p.pump(2.1);qmp,nmp=op(s,9,9);_,s,_=send(qmp,nmp,b'consumed');drunk=time.monotonic();p.pump(.15)
 world=reply(10);assert first(p.entities[p.id],8)==first(world,9)
 assert not fields(s[5][9]),s
 p.logout();p=connect();p.select(p.characters[0][0]);walk=walker(p,first,.3);assert bag()==s
 replay,_,_=send(qmp,nmp,b'consumed');assert first(replay,2)==b'consumed' and bag()==s
 # Potion activation overlapping an armed attack. A 7 HP reference worm falls to
 # one armed hit, so the in-range cooldown/expiry audit of the frozen weapon
 # interval cannot run here; server admission tests cover it (see below).
 for source,style in [(0,2),(3,4)]:
  s=bag();qgear,ngear=op(s,5,source);_,s,_=send(qgear,ngear,b'committed')
  p.pump(.2);assert first(p.entities[p.id],22)==style
  # Each drink below must start after the last one's lockout: a missed strike
  # leaves the previous pass's worm at full health beside the player, and
  # drinking at it at once starts about 1.3 s after the last drink's reply (PQ-428).
  rested();deadline=time.monotonic()+40;npc=None
  while time.monotonic()<deadline and npc is None:p.pump(.2);npc=nearest(full=True)
  assert npc,'no fresh target for the overlap audit'
  target=first(npc,1);approach(npc)
  s=bag();drink,drink_name=op(s,9);p.send(32,drink)
  p.action_seq+=1;p.send(15,integer(1,p.session)+integer(2,p.action_seq)+integer(3,target)+blob(4,p.action_id))
  drank=attacked=None;deadline=time.monotonic()+8
  while (drank is None or attacked is None) and time.monotonic()<deadline:
   tag,data=p.receive();assert tag!=4,(tag,data)
   if tag==33 and first(data,1)==drink_name:drank=data;drunk=time.monotonic()
   if tag==16 and first(data,1)==p.action_seq:attacked=data
  assert drank and first(drank,2)==b'consumed',drank
  assert attacked and first(attacked,2) in (b'hit',b'miss'),attacked
  after=fields(first(drank,3));assert first(fields(after[5][1]),3)==first(fields(s[5][1]),3)-1
  p.pump(.1);assert first(p.entities[p.id],23)==style
  s=bag();sequence+=1;name=('cp-'+str(sequence)).encode()
  qgear=integer(1,6)+blob(2,name)+integer(3,first(s,1))+integer(5,source)+integer(6,first(fields(s[6][0]),1))
  _,s,_=send(qgear,name,b'committed');p.pump(.1);assert first(p.entities[p.id],22)==1
 print('SKIP live blade/two-hand cooldown expiry audit: reference worms (7 HP) do not survive an armed hit; server/gameplay.rs admission tests cover weapon intervals')
 print('PASS TLS potion activation overlaps blade/two-hand combat and preserves one-item consumption')
 print('PASS TLS moving-strike identity, unarmed cooldown, delayed real HP/MP recovery, shared lockout, exact retry and reconnect item conservation')
 p.logout()
finally:p.s.close()
