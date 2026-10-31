"""Original equipment fixture and real transaction authority/recovery checks."""
import json,shutil,sys,time
from pathlib import Path
from world_peer import fields,first,integer,blob
from isolation import once_per_run

@once_per_run
def prepare():
    from repair_live import prepare as repair_prepare
    repair_prepare();root=Path('build/ko-completion/equipment/source');root.mkdir(parents=True,exist_ok=True)
    shutil.copytree('build/ko-completion/repair/source',root,dirs_exist_ok=True)
    m=json.loads((root/'package.json').read_text());m['engine_version']=18;m['protocol_version']=11
    m['inventory']['capacity']=32
    defs=[('shield','Shield'),('twohand','Two hand blade'),('ring','Ring'),('other_race','Restricted race'),('strong','High strength'),('titled','High title')]
    for id,label in defs:
        m['inventory']['items'].append({'id':'demo:item/'+id,'label':label,'stack_limit':1,'durability':80,'starting':1})
        m['commerce']['items'].append({'id':'demo:item/'+id,'weight':2,'price':120,'sell_divisor':6})
    def item(id,slots,blocks=[],race=0,title=0,attributes=[0]*5,swappable=False):
        return dict(id='demo:item/'+id,slots=slots,blocks=blocks,race=race,title=title,attributes=attributes,swappable=swappable)
    m['equipment']={'race':1,'title':0,'attributes':[60,60,60,50,50],'slots':['Right hand','Left hand','Right ring','Left ring'],
      'items':[item('blade',[0,1],swappable=True),item('shield',[1],race=1),item('twohand',[0],[1]),item('ring',[2,3]),item('other_race',[0],race=2),item('strong',[0],attributes=[61,0,0,0,0]),item('titled',[0],title=1)]}
    (root/'package.json').write_text(json.dumps(m));sys.path.insert(0,str(Path('tools/assetc').resolve()));import main
    package=Path('build/ko-completion/equipment/package');main.cook(root,package);return package.resolve()

def audit(connect,restart,sql):
    p=connect('explorer');peer=connect('companion');requests=0
    def req(q=b'',status=b'ok',actor=None):
        nonlocal requests
        requests+=1
        if peer:peer.pump(.03)
        if requests%7==0:time.sleep(1.05)
        actor=actor or p;actor.send(32,q);tag,r=actor.until(33,4);assert tag==33 and first(r,2)==status,(tag,r,status)
        return r,fields(first(r,3))
    def tx(name,state,op,src,dst,serial=None):
        records=state[6] if op in (6,7) else state[5]
        return integer(1,op)+blob(2,name)+integer(3,first(state,1))+integer(4,src)+integer(5,dst)+integer(6,serial if serial is not None else first(fields(records[src]),1))
    _,s=req();_,other=req(actor=peer);initial=s;serial=first(fields(s[5][0]),1)
    for name,src,dst,status in [('bad-slot',0,3,b'incompatible_slot'),('race',5,0,b'requirements'),('base',6,0,b'requirements'),('title',7,0,b'requirements'),('potion',1,0,b'not_equippable')]:
        _,same=req(tx(name,s,5,src,dst),status);assert same==s
    _,same=req(tx('foreign',s,5,0,0,first(fields(other[5][0]),1)),b'instance_conflict');assert same==s
    equip=tx('equip',s,5,0,0)
    sql("CREATE FUNCTION fail_gear() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'equipment rollback'; END $$; CREATE TRIGGER fail_gear BEFORE INSERT ON bag_operations FOR EACH ROW EXECUTE FUNCTION fail_gear()")
    p.send(32,equip);assert first(p.until(4)[1],1)==4
    sql('DROP TRIGGER fail_gear ON bag_operations; DROP FUNCTION fail_gear()');_,same=req();assert same==s
    result,s=req(equip,b'committed');assert not fields(s[5][0]) and first(fields(s[6][0]),1)==serial
    replay,_=req(equip,b'committed');assert replay==result
    purchase=integer(1,2)+blob(2,'equipped-weight')+integer(3,first(s,1))+integer(4,9)+blob(7,'demo:shop/supplies')+blob(8,'demo:item/potion')+integer(9,1)
    _,same=req(purchase,b'weight_limit');assert same==s
    _,same=req(tx('stale',initial,5,0,0),b'revision_conflict');assert same==s
    _,s=req(tx('shield',s,5,2,1),b'committed')
    _,same=req(tx('two-occupied',s,5,3,0),b'equipment_full');assert same==s
    _,same=req(tx('unequip-occupied',s,6,0,1),b'occupied_slot');assert same==s
    _,s=req(tx('unequip-blade',s,6,0,0),b'committed')
    shield=fields(s[6][1]);twohand=fields(s[5][3])
    _,s=req(tx('two-displaces-shield',s,5,3,0),b'committed')
    assert fields(s[5][3])==shield and fields(s[6][0])==twohand and not fields(s[6][1])
    _,s=req(tx('blade-displaces-two',s,5,0,1),b'committed')
    assert fields(s[5][0])==twohand and not fields(s[6][0]) and first(fields(s[6][1]),1)==serial
    _,s=req(tx('move-hands',s,7,1,0),b'committed')
    assert first(fields(s[6][0]),1)==serial
    _,s=req(tx('ring',s,5,4,2),b'committed')
    _,s=req(tx('ring-move',s,7,2,3),b'committed')
    assert not fields(s[6][2]) and first(fields(s[6][3]),2)==b'demo:item/ring'
    replay,_=req(equip,b'committed');assert replay==result
    _,latest=req();assert latest==s
    from repair_live import encode,damage
    import copy
    broken=copy.deepcopy(s);broken[1]=[first(s,1)+1];slot=fields(broken[6][0]);slot[4]=[10];broken[6][0]=encode(slot)
    sql("UPDATE character_bags b SET state=decode('"+encode(broken).hex()+"','hex') FROM characters c WHERE b.character_id=c.id AND c.name='Explorer'")
    _,s=req();assert s==broken
    repair=integer(1,8)+blob(2,'repair-equipped')+integer(3,first(s,1))+integer(6,first(fields(s[6][0]),1))+blob(8,'demo:item/blade')
    sql("CREATE FUNCTION fail_gear_repair() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'equipment repair rollback'; END $$; CREATE TRIGGER fail_gear_repair BEFORE INSERT ON bag_operations FOR EACH ROW EXECUTE FUNCTION fail_gear_repair()")
    p.send(32,repair);assert first(p.until(4)[1],1)==4
    sql('DROP TRIGGER fail_gear_repair ON bag_operations; DROP FUNCTION fail_gear_repair()')
    _,same=req();assert same==s
    repaired,s=req(repair,b'committed');assert first(s,4)==56 and first(fields(s[6][0]),4)==80 and first(fields(s[6][0]),1)==serial
    again,_=req(repair,b'committed');assert again==repaired
    _,same=req(actor=peer);assert same==other
    damage(sql,'Companion',other)
    ids=[first(fields(r),1) for r in s[5]+s[6] if fields(r)];assert len(ids)==len(set(ids))
    peer.logout();peer=None;p.logout();restart();p=connect('explorer')
    _,saved=req();assert saved==s
    replay,_=req(equip,b'committed');assert replay==result
    replay,_=req(repair,b'committed');assert replay==repaired
    p.logout();print('PASS equipment requirements, exclusions, atomic displacement/rollback, instance ownership, slot bounds, immutable retry, isolation, equipped repair/rollback and hard restart',flush=True)
