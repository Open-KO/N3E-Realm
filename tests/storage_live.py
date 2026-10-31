"""Original account storage fixture and TLS transaction/recovery checks."""
import json,shutil,sys,time
from pathlib import Path
from world_peer import DISCONNECTED,fields,first,integer,blob
from isolation import once_per_run

@once_per_run
def prepare():
    from wear_live import prepare as wear_prepare
    wear_prepare();root=Path('build/ko-completion/storage/source');root.mkdir(parents=True,exist_ok=True)
    shutil.copytree('build/ko-completion/wear/source',root,dirs_exist_ok=True)
    m=json.loads((root/'package.json').read_text());m['engine_version']=21;m['protocol_version']=14
    m['gameplay']['spawns']=[[-5,-5]];m['gameplay']['npc_cooldown_ticks']=4;m['damage']['npc']['attack']=3
    m['storage']={'capacity':192,'coin_limit':2100000000,'services':[{'id':'demo:bank/test','label':'Account Warehouse','position':[0,0,0],'radius':11,'remote':False,'open_fee':10}]}
    (root/'package.json').write_text(json.dumps(m));sys.path.insert(0,str(Path('tools/assetc').resolve()));import main
    package=Path('build/ko-completion/storage/package');main.cook(root,package);return package.resolve()

def audit(connect,restart,sql):
    p=connect('explorer');bag=None;bank=None;seq=0;requests=0
    def recv():
        nonlocal bag,bank
        tag,data=p.receive()
        if tag==33:
            candidate=fields(first(data,3))
            if bag is None or first(candidate,1)>=first(bag,1):bag=candidate
        if tag==35:
            if 3 in data:
                candidate=fields(first(data,3))
                if bag is None or first(candidate,1)>=first(bag,1):bag=candidate
            if 4 in data:
                candidate=fields(first(data,4))
                if bank is None or first(candidate,1)>=first(bank,1):bank=candidate
        return tag,data
    def throttle():
        nonlocal requests
        requests+=1
        if requests%6==0:p.pump(1.05)
    def bagread():
        throttle();p.send(32,b'')
        while True:
            tag,data=recv()
            if tag==33 and first(data,1,b'')==b'':return bag
            assert tag!=4,(tag,data)
    def payload(op,source=0,dest=0,qty=0,name=None):
        nonlocal seq
        seq+=1;name=name or 'storage-'+str(seq)
        serial=first(fields((bag[5]if op==1 else bank[4])[source]),1)if op in(1,2,3)else 0
        return blob(2,name)+integer(1,op)+integer(3,first(bag,1))+integer(4,first(bank or {},1))+blob(5,'demo:bank/test')+integer(6,source)+integer(7,dest)+integer(8,serial)+integer(9,qty)
    def request(q,status=b'committed'):
        throttle();name=first(fields(q),2);p.send(34,q);end=time.monotonic()+4
        while time.monotonic()<end:
            tag,data=recv()
            if tag==35 and first(data,1)==name:
                assert first(data,2)==status,(data,status);return data
            assert tag!=4,(tag,data)
        raise AssertionError(('missing storage reply',name))
    bagread();coins=first(bag,4);opening=payload(0);original=request(opening);assert first(bag,4)==coins-10 and len(bank[4])==192
    blade=fields(bag[5][0]);deposit=payload(1,0,191,1);request(deposit);assert fields(bank[4][191])==blade and not fields(bag[5][0])
    moved=payload(3,191,4);request(moved);assert fields(bank[4][4])==blade
    # Original replay is immutable, but the peer's current cache cannot roll back.
    current_bag=bag;current_bank=bank;assert request(opening)==original;assert bag==current_bag and bank==current_bank
    request(payload(3,4,192),b'invalid_slot');assert bank==current_bank
    request(payload(4,qty=20));saved=bank;p.logout()
    p=connect('explorer',select=False);alt=p.create('WarehouseAlt');assert p.select(alt)[0]==10;bag=bank=None;bagread();request(payload(0));assert bank==saved
    # Carry checks apply to the receiving character's own current gear/level.
    request(payload(2,4,8,1),b'weight_limit');request(payload(1,2,5,1));request(payload(2,4,8,1));assert fields(bag[5][8])==blade
    request(payload(5,qty=7));assert first(bank,3)==13;p.logout()
    p=connect('companion');bag=bank=None;bagread();request(payload(0));assert first(bank,3)==0 and all(not fields(i)for i in bank[4]);p.logout()
    p=connect('explorer');bag=bank=None;bagread();request(payload(0));assert first(bank,3)==13
    # Two real process crash windows, followed by exact operation retry.
    for phase in ['before_commit','after_commit']:
        before_bag=bag;before_bank=bank;count=int(sql('SELECT count(*) FROM storage_operations'))
        q=payload(4,qty=3,name='crash-'+phase);p.logout();restart(storage_fault=phase);p=connect('explorer');bag=bank=None;bagread();p.send(34,q);closed=False
        try:
            end=time.monotonic()+6
            while time.monotonic()<end:
                tag,data=recv();assert tag!=35,('published before fault',phase,data)
        except DISCONNECTED:closed=True  # not a timeout (PQ-126)
        assert closed,('missing storage fault',phase)
        restart(expected_exit=95);p=connect('explorer');bag=bank=None;bagread()
        bank=fields(bytes.fromhex(sql("SELECT encode(s.state,'hex') FROM account_storage s JOIN accounts a ON a.id=s.account_id WHERE a.name='explorer'").strip()))
        delta=1 if phase=='after_commit'else 0
        assert first(bag,4)==first(before_bag,4)-3*delta and first(bank,3)==first(before_bank,3)+3*delta
        assert first(bag,1)==first(before_bag,1)+delta and first(bank,1)==first(before_bank,1)+delta
        assert int(sql('SELECT count(*) FROM storage_operations'))==count+delta
        request(q);assert first(bag,4)==first(before_bag,4)-3 and first(bank,3)==first(before_bank,3)+3
        assert int(sql('SELECT count(*) FROM storage_operations'))==count+1
    # Storage I/O must not provide temporary invulnerability or stop world ticks.
    bagread();gear=integer(1,5)+blob(2,'storage-ring')+integer(3,first(bag,1))+integer(4,4)+integer(5,2)+integer(6,first(fields(bag[5][4]),1));p.send(32,gear)
    while True:
        tag,data=recv()
        if tag==33 and first(data,1,b'')==b'storage-ring':assert first(data,2)==b'committed';break
    p.logout();p=connect('explorer');bag=bank=None;bagread()
    bank=fields(bytes.fromhex(sql("SELECT encode(s.state,'hex') FROM account_storage s JOIN accounts a ON a.id=s.account_id WHERE a.name='explorer'").strip()))
    end=time.monotonic()+10
    while time.monotonic()<end:
        tag,data=recv()
        if tag!=10:continue
        me=p.entities[p.id];npc=next(e for e in p.entities.values()if first(e,9));dx=first(npc,3)-first(me,3);dz=first(npc,5)-first(me,5);distance=(dx*dx+dz*dz)**.5
        if distance<1.2:p.move(0,0);break
        p.move(dx/max(1,distance),dz/max(1,distance))
    else:raise AssertionError(('NPC approach',p.entities,p.session))
    # A ring is not worn by ordinary attacks; incoming hits need no database wear.
    sql("CREATE FUNCTION delay_storage() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_sleep(.3); RETURN NEW; END $$; CREATE TRIGGER delay_storage BEFORE INSERT ON storage_operations FOR EACH ROW EXECUTE FUNCTION delay_storage()")
    # Each delayed deposit must see world ticks; damage must land during one of
    # them. A 0.3 s window holds one or two sentinel strikes (4-tick cooldown)
    # and each misses 10 % of the time (accuracy/evasion 1), so one window had no
    # hit about one run in twenty (PQ-154). Repeat windows until a hit, bounded
    # by 8 resolved sentinel strikes seen inside them (a spurious failure about
    # 1e-8) and, should the sentinel stop striking, by 20 windows.
    strikes=0;windows=[]
    def striking():
        npc=next((e for e in p.entities.values()if first(e,9)),{});return first(npc,10),first(npc,14,b'')
    while True:
        health=first(p.entities[p.id],7);seen=striking()[0];q=payload(4,qty=1);p.send(34,q);worlds=0;damaged=False
        while True:
            tag,data=recv()
            if tag==10:
                worlds+=1;damaged|=first(p.entities[p.id],7)<health;at,result=striking()
                if at!=seen:seen=at;strikes+=result in(b'hit',b'miss')
            if tag==35 and first(data,1)==first(fields(q),2):assert first(data,2)==b'committed';break
            assert tag!=4,(tag,data)
        windows.append((worlds,damaged));assert worlds>=3,('storage paused world ticks',windows)
        if damaged:break
        assert strikes<8 and len(windows)<20,('storage paused combat',strikes,windows)
    sql('DROP TRIGGER delay_storage ON storage_operations;DROP FUNCTION delay_storage()');p.logout()
    # Freeze a real outgoing wear event, then attempt storage before it commits.
    p=connect('explorer',select=False);alt=next(i for i,n in p.characters if n=='WarehouseAlt');assert p.select(alt)[0]==10;bag=bank=None;bagread();request(payload(0))
    def gear(name,op,source,dest):
        throttle();records=bag[6]if op==6 else bag[5]
        q=integer(1,op)+blob(2,name)+integer(3,first(bag,1))+integer(4,source)+integer(5,dest)+integer(6,first(fields(records[source]),1));p.send(32,q)
        while True:
            tag,data=recv()
            if tag==33 and first(data,1,b'')==name.encode():assert first(data,2)==b'committed';return
            assert tag!=4,(tag,data)
    gear('storage-wear-blade',5,8,0);gear('storage-wear-ring',5,4,2)
    # Retain this authenticated session and allow regeneration before approaching.
    p.pump(3);bagread()
    end=time.monotonic()+10
    while time.monotonic()<end:
        tag,data=recv()
        if tag!=10:continue
        me=p.entities[p.id];npc=next(e for e in p.entities.values()if first(e,9));dx=first(npc,3)-first(me,3);dz=first(npc,5)-first(me,5);distance=(dx*dx+dz*dz)**.5
        if distance<.9:p.move(0,0);break
        p.move(dx/max(1,distance),dz/max(1,distance))
    else:raise AssertionError('wear/storage approach')
    sql("CREATE FUNCTION delay_storage_wear() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_sleep(.3); RETURN NEW; END $$; CREATE TRIGGER delay_storage_wear BEFORE INSERT ON durability_operations FOR EACH ROW EXECUTE FUNCTION delay_storage_wear()")
    serial=first(fields(bag[6][0]),1);before=first(fields(bag[6][0]),4);denied=False;hit=False
    # Strikes hit 92 % (the wear fixture's sentinel evasion 1): 10 attempts leave a
    # spurious no-hit failure at 0.08**10; 5 left 3e-6 (PQ-123).
    for attempt in range(10):
        p.action_seq+=1;p.send(15,integer(1,p.session)+integer(2,p.action_seq)+integer(3,first(npc,1))+blob(4,p.action_id))
        # Commands are FIFO; one world update allows the admitted event to freeze.
        while True:
            tag,data=recv()
            if tag==16:break
            if tag==10:
                q=integer(1,1)+blob(2,'pending-deposit-'+str(attempt))+integer(3,first(bag,1))+integer(4,first(bank,1))+blob(5,'demo:bank/test')+integer(6,8)+integer(7,6)+integer(8,serial)+integer(9,1)
                p.send(34,q);break
        end=time.monotonic()+3
        while time.monotonic()<end:
            if tag==35 and first(data,2)==b'combat_pending':denied=True
            if tag==16:
                if first(data,2)==b'hit':hit=True
                break
            tag,data=recv()
        if hit:break
        p.pump(1.05)
    assert hit and denied,('wear/storage ordering',hit,denied)
    sql('DROP TRIGGER delay_storage_wear ON durability_operations;DROP FUNCTION delay_storage_wear()');bagread();assert first(fields(bag[6][0]),4)<before
    worn=fields(bag[6][0]);gear('storage-wear-unequip',6,0,8);request(payload(1,8,6,1));assert fields(bank[4][6])==worn
    p.logout()
    print('PASS account-shared storage, weight/bounds/isolation, immutable replies, before/after-COMMIT crashes, exact recovery and combat during delayed storage, and pending wear before deposit',flush=True)
