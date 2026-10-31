"""Native UIF transactions against the prepared isolated Moradon stack.

Uses a fresh audit account; Explorer/Companion and their inventories are untouched.
"""
import argparse,json,os,pathlib,secrets,shutil,subprocess,sys,time,threading
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from world_peer import Peer,fields,first,integer,blob
import moradon_stack
p=argparse.ArgumentParser();p.add_argument('--loot-expiry',action='store_true');p.add_argument('--melee-start',action='store_true');p.add_argument('--skills',action='store_true');p.add_argument('--target-marker',action='store_true');p.add_argument('--loot-chests',action='store_true');p.add_argument('--nameplates',action='store_true');p.add_argument('--hotbar',action='store_true');p.add_argument('--potions',action='store_true');p.add_argument('--moving-attacks',action='store_true');p.add_argument('--weapon-animations',action='store_true');p.add_argument('--rest-items',action='store_true');p.add_argument('--tools',action='store_true');p.add_argument('--next-three',action='store_true');p.add_argument('--drag',action='store_true');p.add_argument('--size',default='1024x768');p.add_argument('--fullscreen',action='store_true');a=p.parse_args()
root=pathlib.Path(__file__).resolve().parents[1];os.chdir(root)
# What the test client's replays need from this fixture (PQ-006): the Moradon
# package's items by role and the warehouse password provisioned below.
ITEMS={'potion':'demo:item/potion','mana_potion':'demo:item/mana_potion','blade':'demo:item/blade',
       'twohand':'demo:item/twohand','shield':'demo:item/shield'}
STORAGE_PASSWORD='Moradon1'
state=moradon_stack.state()
package=(root/moradon_stack.PACKAGE).resolve();recipe=json.loads((package/'recipe.json').read_text())['manifest']
assert state['release']==(package/'release.sha256').read_text().strip()
work=root/'build/ko-completion/uif';work.mkdir(parents=True,exist_ok=True)
env={**os.environ,'N3E_IMAGE':moradon_stack.IMAGE,'N3E_PACKAGE_PATH':str(package),'N3E_PORT':str(state['port']),'N3E_REALM':state['realm']}
account='uif'+secrets.token_hex(6);password=secrets.token_urlsafe(24)
base=['docker','compose','-p',moradon_stack.PROJECT,'exec','-T','server','n3e-server']
subprocess.run(base+['account-create',account],input=password+'\n',text=True,env=env,capture_output=True,check=True)
subprocess.run(base+['storage-password-init',account],input=STORAGE_PASSWORD+'\n',text=True,env=env,capture_output=True,check=True)
peer=Peer(state['port'],account,password,content=state['release'],game=recipe['game_id'],protocol=recipe['protocol_version'])
name=('WiMi' if a.nameplates else 'Uif')+secrets.token_hex(4);character=peer.create(name);peer.s.close()
# PQ-177: the nameplate replay's character holds the inspection capability, so
# the server projects it and the client draws the package's NPC info line.
if a.nameplates:subprocess.run(base+['role','grant',account,str(character),state['realm'],'server.inspect'],env=env,capture_output=True,check=True)
env.update(N3E_TEST_ACCOUNT=account,N3E_TEST_PASSWORD=password,N3E_TEST_UIF_ACTIONS='1',N3E_TEST_UIF_NAME=name,
           N3E_TEST_ITEMS=';'.join(f'{role}={item}' for role,item in ITEMS.items()),N3E_TEST_STORAGE_PASSWORD=STORAGE_PASSWORD)
if a.skills:env.pop('N3E_TEST_UIF_ACTIONS',None);env['N3E_TEST_SKILLS']='1';env['N3E_TEST_EFFECTS']='1';env['XDG_STATE_HOME']=str(work/'hotbar-state')
if a.target_marker:env.pop('N3E_TEST_UIF_ACTIONS',None);env['N3E_TEST_TARGET_MARKER']='1'
if a.nameplates:env.pop('N3E_TEST_UIF_ACTIONS',None);env['N3E_TEST_NAMEPLATES']='1';env['N3E_TEST_NPC_INFO']='1'
# PQ-288: the client reports each worm's drawn scale, placed box and name height.
if a.nameplates:env['N3E_TEST_NPC_LOOKS']='1'
if a.drag:env.pop('N3E_TEST_UIF_ACTIONS');env['N3E_TEST_UIF_DRAG']='1'
if a.loot_expiry:a.loot_chests=True;a.melee_start=True;env['N3E_TEST_LOOT_EXPIRY']='1'
if a.melee_start:env['N3E_TEST_MELEE_START']='1';env['N3E_TEST_MELEE_SEQUENCE']='1'
if a.loot_chests:a.next_three=True;env['N3E_TEST_LOOT_CHESTS']='1'
if a.next_three:env.pop('N3E_TEST_UIF_ACTIONS',None);env['N3E_TEST_NEXT_THREE']='1'
if a.moving_attacks:a.weapon_animations=True;env['N3E_TEST_MOVING_ATTACKS']='1'
if a.hotbar:env.pop('N3E_TEST_UIF_ACTIONS',None);env['N3E_TEST_HOTBAR']='1';env['XDG_STATE_HOME']=str(work/'hotbar-state')
if a.potions:env.pop('N3E_TEST_UIF_ACTIONS',None);env['N3E_TEST_POTIONS']='1';env['XDG_STATE_HOME']=str(work/'hotbar-state')
if a.weapon_animations:env['N3E_TEST_MELEE_SEQUENCE']='1'
if a.weapon_animations:env.pop('N3E_TEST_UIF_ACTIONS',None);env['N3E_TEST_WEAPON_ANIMATIONS']='1'
if a.rest_items:env.pop('N3E_TEST_UIF_ACTIONS',None);env['N3E_TEST_REST_ITEMS']='1'
name=('tools-' if a.tools else '')+('skills' if a.skills else 'target-marker' if a.target_marker else 'chests' if a.loot_chests else 'nameplates' if a.nameplates else 'hotbar' if a.hotbar else 'potions' if a.potions else 'moving' if a.moving_attacks else 'weapons' if a.weapon_animations else 'rest-items' if a.rest_items else 'next-three' if a.next_three else 'drag' if a.drag else 'actions')+('' if a.size=='1024x768' else '-'+a.size)+('-fullscreen' if a.fullscreen else '')
if a.loot_expiry:name=name.replace('chests','expiry')
elif a.melee_start:name=name.replace('chests','approach-chests')
# Reference worms live outside the town walls: modes that need them walk the
# build-verified route once, at the stage where they first look for a worm.
route_stage=0 if a.target_marker else 3 if a.nameplates else 9 if a.skills else 25 if a.next_three else 2 if a.weapon_animations else None
smoke='90'
if route_stage is not None:
    route=json.loads((root/moradon_stack.PROVENANCE).read_text())['features']['worm'][0]['route']
    env.update(N3E_TEST_ROUTE=';'.join(f'{x},{z}' for x,z in route),N3E_TEST_ROUTE_STAGE=str(route_stage));smoke='240'
client=root/('build/client-tools/n3e-test-client' if a.tools else 'build/client/n3e-test-client')
cmd=[str(client),str(package),'--connect','localhost:'+str(state['port']),'--ca','deploy/local/ca.pem','--auto-login','--fixed-window',a.size,*(['--fullscreen'] if a.fullscreen else []),'--world-smoke',smoke,'--capture',str(work/name)]
observer=None;observer_stop=threading.Event();observer_errors=[]
if a.nameplates:
    observer_account='names'+secrets.token_hex(6);observer_password=secrets.token_urlsafe(24)
    subprocess.run(base+['account-create',observer_account],input=observer_password+'\n',text=True,env=env,capture_output=True,check=True)
    observer=Peer(state['port'],observer_account,observer_password,content=state['release'],game=recipe['game_id'],protocol=recipe['protocol_version'])
    observer_name='Ili'+secrets.token_hex(2)
    observer.select(observer.create(observer_name))
    for _ in range(12):observer.move(1,0);observer.pump(.1)
    observer.move(0,0)
    # PQ-166: with a party-name policy the replay, once at the worms, invites the
    # observer. It accepts, then runs the worm route's first leg to 52 % of its
    # length (about 56 m short of the worm point, inside the replay's 32 m interest
    # cells again), so its name comes back beyond the 48 m camera limit.
    party_names=recipe['input']['names'].get('party')
    if party_names:env['N3E_TEST_PARTY_PEER']=observer_name
    leg=json.loads((root/moradon_stack.PROVENANCE).read_text())['features']['worm'][0]['route'][:2]
    stop=[leg[0][i]+.52*(leg[1][i]-leg[0][i]) for i in range(2)]
    observer_party={'joined':False}
    def keep_observer():
        try:
            ping=0;legs=[]
            while not observer_stop.is_set():
                if time.monotonic()>=ping:observer.send(14);ping=time.monotonic()+.75
                tag,data=observer.receive()
                if tag==43 and first(data,5)>0 and not observer_party['joined']:
                    observer.send(42,integer(1,1)+integer(2,2)+integer(4,first(data,5)))
                elif tag==44 and first(data,2)==b'joined':
                    observer_party['joined']=True;legs=[leg[0],stop]
                elif tag==10 and legs and first(observer.entities[observer.id],6)>=observer.seq:
                    me=observer.entities[observer.id];dx=legs[0][0]-first(me,3);dz=legs[0][1]-first(me,5);d=(dx*dx+dz*dz)**.5
                    if d>=.7:observer.move(dx/max(1,d),dz/max(1,d),mode=1)
                    else:
                        legs.pop(0)
                        if not legs:observer.move(0,0)
        except Exception as e:observer_errors.append(e)
    observer_thread=threading.Thread(target=keep_observer);observer_thread.start()
client_process=subprocess.Popen(cmd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
try:
    # Focus only our replay window; desktop focus is otherwise nondeterministic.
    # This is an optional test adapter, not a compositor/config dependency. An
    # offscreen client (make live-ko's default, PQ-129) has no window to focus.
    if os.environ.get('HYPRLAND_INSTANCE_SIGNATURE') and shutil.which('hyprctl') and os.environ.get('SDL_VIDEO_DRIVER')!='offscreen':
        for _ in range(50):
            if client_process.poll() is not None:break
            windows=subprocess.run(['hyprctl','clients','-j'],capture_output=True,text=True)
            if windows.returncode:break
            owned=next((w for w in json.loads(windows.stdout)if w.get('pid')==client_process.pid),None)
            if owned:
                address='address:'+owned['address']
                focus=subprocess.run(['hyprctl','eval','hl.dispatch("focuswindow", '+json.dumps(address)+')'],capture_output=True,text=True)
                if focus.returncode:subprocess.run(['hyprctl','dispatch','focuswindow',address],capture_output=True)
                break
            time.sleep(.1)
    stdout,stderr=client_process.communicate(timeout=int(smoke)+60)
finally:
    if client_process.poll() is None:client_process.kill();client_process.wait()
    if observer:
        observer_stop.set();observer_thread.join();observer.logout();observer.s.close()
(work/(name+'.log')).write_text(stdout+stderr)
assert not observer_errors,observer_errors
assert client_process.returncode==0 and 'PASS UIF SDL' in stdout,stdout+stderr
if env.get('N3E_TEST_LOOT_RANGE'):
    assert 'PASS distant chest inspection with authoritative out-of-range pickup rejection' in stdout,stdout
if env.get('N3E_TEST_MELEE_SEQUENCE'):
    import re
    predicted=re.findall(r'MELEE_PREDICT request=(\d+) delay=([\d.]+) server=(\d+)',stdout)
    confirmed=re.findall(r'MELEE_CONFIRM request=(\d+) elapsed=([\d.]+) hit=([01])',stdout)
    assert predicted and confirmed,('missing swing reconciliation evidence',stdout)
    assert len({v[0] for v in predicted})==len(predicted),('swing restarted',predicted)
    assert all(float(v[1])<=.05 and v[0]!=v[2] for v in predicted),predicted
    assert all(any(p[0]==v[0] for p in predicted) for v in confirmed),confirmed
if a.skills:
    # PQ-481 (D-245): Light Strike's right-button copy is refused at level 1
    # and made after the level-up, before the strike is cast from the hotbar.
    import re
    locked=re.findall(r'^SKILL_LOCKED_COPY_REFUSED skill=(\S+) level=(\d+)$',stdout,re.M)
    unlocked=re.findall(r'^SKILL_UNLOCKED_COPY skill=(\S+) level=(\d+)$',stdout,re.M)
    assert len(locked)==1 and len(unlocked)==1 and locked[0][0]==unlocked[0][0] and int(locked[0][1])<int(unlocked[0][1]),(locked,unlocked)
    assert stdout.index('SKILL_LOCKED_COPY_REFUSED')<stdout.index('SKILL_UNLOCKED_COPY'),stdout[-2000:]
    print('PASS locked skill copy refused at level',locked[0][1],'and made at level',unlocked[0][1],flush=True)
if env.get('N3E_TEST_EFFECTS') and (a.skills or a.potions):
    required=['heal-cast','heal-target']+(['strike-cast','strike-target'] if a.skills else ['resource-target'])
    for key in required:
        prefix=str(work/name)+'.effect-'+key
        assert 'EFFECT_CAPTURE '+prefix+'\n' in stdout,('missing current-run FX capture',key)
        before=pathlib.Path(prefix+'.before.ppm').read_bytes()
        after=pathlib.Path(prefix+'.after.ppm').read_bytes()
        changed=sum(x!=y for x,y in zip(before,after))
        assert len(before)==len(after) and changed>0,('empty FX draw',key)
        print('PASS effect pixels',key,changed)
if a.nameplates:
    # PQ-169: the observer waits near the spawn while the replay walks out to the
    # worms. Its label must be made inside the package's acquire radius, kept
    # between the radii and dropped beyond the release radius, never otherwise.
    import re
    life=recipe['input']['names']['lifetime']
    assert life['from']=='self' and life['exempt']==['party'],life
    lines=re.findall(r'NAME_LIFETIME (acquired|released|kept) entity=(\d+) distance=([-\d.e+naif]+)(?: exempt=(\d+))?',stdout)
    events=[(kind,float(d),int(x or 0)) for kind,e,d,x in lines if int(e)==observer.id]
    seen=[(kind,d) for kind,d,x in events if not x]
    assert all(d<life['acquire'] for kind,d in seen if kind=='acquired'),seen
    assert all(d>life['release'] for kind,d in seen if kind=='released'),seen
    assert all(life['acquire']<=d<=life['release'] for kind,d in seen if kind=='kept'),seen
    assert [k for k,_ in seen][:3]==['acquired','kept','released'],('observer label lifetime',seen)
    print('PASS observer label made at',seen[0][1],'m, kept at',seen[1][1],'m, dropped at',seen[2][1],'m')
    if party_names:
        # PQ-166: as a party member the observer's label is made at any range,
        # drawn beyond the camera limit in the party colour, and kept under O.
        assert observer_party['joined'],observer_party
        exempt=[d for kind,d,x in events if kind=='acquired' and x]
        assert exempt and exempt[0]>life['release'],('party label at any range',events)
        drawn=re.search(r'NAME_PARTY drawn entity=(\d+) camera=([\d.]+) limit=([\d.]+) color=(\d+)',stdout)
        assert drawn and int(drawn[1])==observer.id and float(drawn[2])>float(drawn[3]),('party name beyond the camera limit',drawn and drawn[0])
        assert party_names['beyond_distance'] and int(drawn[4])==party_names['color'],('party colour',drawn[0])
        hidden=re.search(r'NAME_PARTY hidden entity=(\d+) kept=(\d)',stdout)
        assert hidden and int(hidden[1])==observer.id and hidden[2]==str(int(party_names['while_hidden'])),('party name under the toggle',hidden and hidden[0])
        print('PASS party member label made at',exempt[0],'m, drawn at',drawn[2],'m from the camera (limit',drawn[3]+') in colour',hex(int(drawn[4])),', kept under the toggle')
    # PQ-174: NPC names exist only from a frame that finds the NPC under
    # `acquire` until one that finds it in [acquire, release) (KO 00470900);
    # a dead NPC loses its name once its death clip has played (state 5).
    npc_life=recipe['input']['names']['npc_lifetime']
    assert npc_life['rule']=='band' and npc_life['drop_dead'] and not npc_life['always'],npc_life
    npc=[(k,int(e),float(d),dead) for k,e,d,dead in re.findall(r'NPC_NAME_LIFETIME (acquired|released|kept) entity=(\d+) distance=([-\d.e+naif]+)(?: dead=([01]))?',stdout)]
    assert any(k=='acquired' for k,*_ in npc),('no NPC name made',npc)
    assert all(d<npc_life['acquire'] for k,e,d,dead in npc if k=='acquired'),npc
    assert all(dead=='1' or npc_life['acquire']<=d<npc_life['release'] for k,e,d,dead in npc if k=='released'),npc
    assert all(d>=npc_life['release'] for k,e,d,dead in npc if k=='kept'),('NPC name kept inside the band',npc)
    killed=re.search(r'NAME_NPC dead entity=(\d+) named_while_dying=([01])',stdout)
    assert killed and killed[2]=='1',('dead NPC name',killed and killed[0])
    assert any(k=='released' and e==int(killed[1]) and dead=='1' for k,e,d,dead in npc),('dead NPC released',npc)
    # PQ-199: the slain worm is in the actor pick and B while it dies and in
    # neither once its death clip has ended (KO 00470900 moves it to the corpse
    # map at state 5); the replay fails on a violation and reports what it saw.
    picked=re.search(r'PICK_NPC dying picked=([01]) b=([01]) dead picked=0 b=0 entity=(\d+)',stdout)
    assert picked and picked[3]==killed[1] and picked[1]=='1' and picked[2]=='1',('slain NPC pick window',picked and picked[0])
    away=re.search(r'NAME_NPC walked away named=(\d+)',stdout)
    assert away and away[1]=='0',('NPC names left after walking away',away and away[0])
    ranged=[d for k,e,d,dead in npc if k=='released' and dead=='0']
    assert ranged,('no NPC name dropped by range',npc)
    # PQ-177: every NPC name drawn at the first named-worm frame carried the
    # package's info line (checked in the replay: text, colour, placement).
    info=recipe['input']['names']['npc_info']
    lines=re.findall(r'NAME_NPC_INFO entity=(\d+) text=(.*) color=(\d+) y=(-?\d+) name_y=(-?\d+)',stdout)
    # PQ-186: no NPC is traced in this replay, so {state:0} shows its fallback 0.
    assert lines and all(t==info['text'].replace('{id}',e).replace('{state:0}','0') and int(c)==info['color'] for e,t,c,y,ny in lines),('NPC info line',lines)
    print('PASS NPC info line above',len(lines),'NPC names with server.inspect:',lines[0][1],'at y',lines[0][3],'over the name at',lines[0][4])
    # PQ-288: every worm is drawn at its K_MONSTER sSize (120 % for row 750):
    # the package's NPC set carries it as its instance scale, no template scale
    # reaches it on the wire (Entity.scale 0, factor 1), and its name sits at the
    # nameplate style's NPC height (the worm skeleton's, at that scale) plus the
    # style's padding (KO 00459820: y + h x s + 0.1 x h x s).
    size=json.loads((root/'games/moradon/ko-reference.json').read_text())['monster']['sSize']
    sets={int(e):(float(k),float(m),float(h)) for e,k,m,h in re.findall(r'^NPC_SET_SCALE entity=(\d+) scale=(\S+) model_scale=(\S+) box_height=(\S+)$',stdout,re.M)}
    labels={int(e):float(h) for e,h in re.findall(r'^NPC_LABEL entity=(\d+) height=(\S+) style=1$',stdout,re.M)}
    assert sets and all(k==1 and abs(m-size/100)<1e-5 for k,m,h in sets.values()),('worm drawn scale',size,sets)
    names=json.loads((root/moradon_stack.PROVENANCE).read_text())['hud']['nameplates']
    padding=json.loads((root/'games/moradon/nameplates.json').read_text())['height_padding']
    assert abs(names['npc_scale']-size/100)<1e-9,('nameplate NPC scale',names['npc_scale'])
    worm_name=names['profiles'][1][0]*(1+padding)
    assert labels and set(labels)<=set(sets) and all(abs(h-worm_name)<1e-4 for h in labels.values()),('worm name height',worm_name,labels)
    heights=sorted({round(h,4) for _,_,h in sets.values()})
    print('PASS worms drawn at sSize',size,'%: model scale',sorted({m for _,m,_ in sets.values()}),'for',len(sets),'worms, wire scale 1, placed box heights',heights,'m; names at',sorted({round(h,4) for h in labels.values()}),'m (style NPC height',round(names['profiles'][1][0],4),'m x',1+padding,')')
    print('PASS NPC names made below',npc_life['acquire'],'m (',len([1 for k,*_ in npc if k=='acquired']),'), dropped in the band at',min(ranged),'-',max(ranged),'m, kept while dying and dropped after the death clip; picked and B-selected while dying, neither once dead')
if a.target_marker:
    import re
    from target_marker_pixels import verify
    verify(work/name)
    # PQ-296: the worm's marker at its drawn size. KO's symbol scales by the
    # selected actor's radius and height times its scale +0x90 (005c4e20 ->
    # 0045a1d0, 00459ff0), the worm's sSize x 0.01: the cooked NPC profile is the
    # worm skeleton's times that factor, and no template scale reaches the worm
    # on the wire (factor 1), so it draws at 2 x r x s across and 1.3 x h x s high.
    size=json.loads((root/'games/moradon/ko-reference.json').read_text())['monster']['sSize']
    marker=json.loads((root/moradon_stack.PROVENANCE).read_text())['target_marker']
    config=json.loads((root/'games/moradon/target-marker.json').read_text())
    assert marker['npc_scale']==size/100 and marker['profiles'][1]==[v*(size/100) for v in marker['measured_profiles'][1]],marker
    drawn={}
    for e,n,k,h,v,part,mode,x,y,z in re.findall(r'^TARGET_MARKER entity=(\d+) npc=(\d) scale=(\S+) horizontal=(\S+) vertical=(\S+) part=(\d) mode=(\d) x=(\S+) y=(\S+) z=(\S+)$',stdout,re.M):
        drawn.setdefault(int(e),{})[int(part)]=(int(n),float(k),float(h),float(v),int(mode),float(x),float(y),float(z))
    r,h=marker['profiles'][1]
    worms=[parts for parts in drawn.values() if all(p[0]==1 for p in parts.values())]
    assert worms and all(abs(p[1]-1)<1e-6 and abs(p[2]-config['diameter_scale']*r)<1e-4 and abs(p[3]-config['height_scale']*h)<1e-4
                         for parts in worms for p in parts.values()),('worm target marker size',r,h,drawn)
    print('PASS worm target marker at sSize',size,'%:',len(worms),'selected worms drawn at',round(config['diameter_scale']*r,4),'m across (2 x',round(r,4),
          ') and',round(config['height_scale']*h,4),'m high (1.3 x',round(h,4),'); skeleton profile',[round(v,4) for v in marker['measured_profiles'][1]])
if a.next_three:
    # A fresh TLS session must recover exactly the items claimed in the native UI.
    peer=Peer(state['port'],account,password,content=state['release'],game=recipe['game_id'],protocol=recipe['protocol_version'])
    try:
        peer.select(peer.characters[0][0]);peer.send(32);bag=fields(first(peer.until(33)[1],3))
        records=[fields(v)for v in bag.get(5,[])+bag.get(6,[])]
        for definition in recipe['inventory']['items']:
            expected=definition['starting']+(0 if a.loot_expiry else sum(d['quantity'] for d in recipe['progression']['items']['items'] if d['id']==definition['id']))
            if a.loot_expiry and definition['id']=='demo:item/potion':expected-=int(next(line.split()[1] for line in stdout.splitlines() if line.startswith('EXPIRY_POTIONS ')))
            assert sum(first(r,3) for r in records if first(r,2)==definition['id'].encode())==expected,definition['id']
        if a.loot_expiry:
            assert recipe['progression']['ttl']==20
            assert first(bag,4)==recipe['inventory']['starting_currency']
            peer.pump(.3);assert first(peer.entities[peer.id],7)>0
            peer.send(23);assert not peer.until(24)[1].get(1)
            line=next(line for line in stdout.splitlines() if line.startswith('EXPIRING_LOOT '))
            _,operation,encounter,item,quantity=line.split()
            # A fresh session cannot claim the reward after the mesh disappears.
            peer.send(25,integer(1,peer.session)+integer(2,1)+integer(3,peer.id)+integer(4,int(operation))+integer(5,int(encounter))+blob(6,item)+integer(7,int(quantity)))
            result=peer.until(26)[1]
            while first(result,2)==b'pending':result=peer.until(26)[1]
            assert first(result,2)==b'expired',result
            peer.send(27,integer(1,int(operation)))
            assert first(peer.until(26)[1],2)==b'expired'
            print('PASS expired loot stays unavailable after reconnect and late claim/retry')
        else:assert first(bag,4)>recipe['inventory']['starting_currency']
        peer.logout()
    finally:peer.s.close()
if a.potions or a.hotbar:
    peer=Peer(state['port'],account,password,content=state['release'],game=recipe['game_id'],protocol=recipe['protocol_version'])
    try:
        peer.select(peer.characters[0][0]);peer.send(32);bag=fields(first(peer.until(33)[1],3));records=[fields(v)for v in bag.get(5,[])]
        assert sum(first(r,3)for r in records if first(r,2)==b'demo:item/potion')==(3 if a.hotbar else 4)
        assert not any(first(r,2)==b'demo:item/mana_potion' for r in records)
        peer.logout()
    finally:peer.s.close()
if a.rest_items:
    peer=Peer(state['port'],account,password,content=state['release'],game=recipe['game_id'],protocol=recipe['protocol_version'])
    try:
        peer.select(peer.characters[0][0]);peer.send(32);bag=fields(first(peer.until(33)[1],3))
        records=[fields(v)for v in bag.get(5,[])+bag.get(6,[])]
        for definition in recipe['inventory']['items']:
            expected=18 if definition['id']=='demo:item/potion' else definition['starting']
            assert sum(first(r,3) for r in records if first(r,2)==definition['id'].encode())==expected,definition['id']
        assert first(bag,4)==recipe['inventory']['starting_currency']-18*13+5*2
        peer.logout()
    finally:peer.s.close()
print('PASS native '+name+': '+('Z/R attack start, chest/pickup expiry and durable late-claim rejection' if a.loot_expiry else 'skill window, hotbar, cast poses/effects/audio and cooldown' if a.skills else 'target marker selection, camera, ground clearing and HUD layering' if a.target_marker else 'self/remote/mob names, sitting placement and HUD layering' if a.nameplates else 'hotbar registration, activation, cooldown and persistence' if a.hotbar else 'right-click registration, HP/MP hotbar use, tooltip, retry and reconnect' if a.potions else 'moving upper-body attacks for five loadouts' if a.moving_attacks else 'weapon ready/attack profiles for five loadouts' if a.weapon_animations else 'sitting, right-click equipment and stack merge/overflow' if a.rest_items else 'equipped appearance, item tooltips, combat and three pickups' if a.next_three else 'paperdoll and drag inventory/commerce/warehouse/cancellation replay' if a.drag else 'UIF inventory/commerce/warehouse/friend operations'))
