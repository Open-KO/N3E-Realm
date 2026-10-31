"""Damaged item fixtures are injected only into this disposable test realm."""
import copy,json,shutil,sys
from pathlib import Path
from world_peer import fields,first,integer,blob
from isolation import once_per_run

@once_per_run
def prepare():
    from commerce_live import prepare as commerce_prepare
    commerce_prepare();root=Path('build/ko-completion/repair/source');root.mkdir(parents=True,exist_ok=True)
    shutil.copytree('build/ko-completion/commerce/source',root,dirs_exist_ok=True)
    m=json.loads((root/'package.json').read_text());m['engine_version']=17;m['protocol_version']=10
    for item in m['commerce']['items']:
        if item['id']=='demo:item/blade':item['price']=120
    m['repair']={'power':.82,'linear':.0001,'offset':10,'multiplier':1,'items':['demo:item/blade']}
    (root/'package.json').write_text(json.dumps(m));sys.path.insert(0,str(Path('tools/assetc').resolve()));import main
    package=Path('build/ko-completion/repair/package');main.cook(root,package);return package.resolve()

def encode(data):
    return b''.join((integer(k,v) if isinstance(v,int) else blob(k,v)) for k,vs in sorted(data.items()) for v in vs)

def damage(sql,name,state,coins=100):
    state=copy.deepcopy(state);state[1]=[first(state,1)+1];state[4]=[coins]
    item=fields(state[5][0]);item[4]=[10];state[5][0]=encode(item)
    # The SQL is test-only, with fixed character names and hex generated from protobuf.
    sql("UPDATE character_bags b SET state=decode('"+encode(state).hex()+"','hex') FROM characters c WHERE b.character_id=c.id AND c.name='"+name+"'")
    return state

def audit(connect,restart,sql):
    p=connect('explorer');companion=connect('companion')
    def req(q=b'',status=b'ok',actor=None):
        actor=actor or p;actor.send(32,q);tag,r=actor.until(33,4)
        assert tag==33 and first(r,2)==status,(tag,r,status)
        return r,fields(first(r,3))
    def repair(name,state,slot=0,item='demo:item/blade'):
        return integer(1,4)+blob(2,name)+integer(3,first(state,1))+integer(4,slot)+integer(6,first(fields(state[5][slot]),1))+blob(8,item)
    _,initial=req();damage(sql,'Explorer',initial,43);_,broken=req()
    q=repair('poor',broken);denied,_=req(q,b'insufficient_currency')
    _,same=req();assert same==broken
    damage(sql,'Explorer',broken,100);_,funded=req()
    replay,_=req(q,b'insufficient_currency');assert replay==denied
    _,same=req();assert same==funded
    _,same=req(repair('potion',funded,1,'demo:item/potion'),b'not_repairable');assert same==funded
    _,same=req(repair('wrong-item',funded,1),b'item_conflict');assert same==funded
    import time;time.sleep(1.05)
    valid=repair('repair-1',funded)
    sql("CREATE FUNCTION fail_repair() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'repair rollback'; END $$; CREATE TRIGGER fail_repair BEFORE INSERT ON bag_operations FOR EACH ROW EXECUTE FUNCTION fail_repair()")
    p.send(32,valid);assert first(p.until(4)[1],1)==4
    sql('DROP TRIGGER fail_repair ON bag_operations; DROP FUNCTION fail_repair()')
    _,same=req();assert same==funded
    result,fixed=req(valid,b'committed')
    assert first(fixed,4)==56 and first(fields(fixed[5][0]),4)==80,(fixed,funded)
    assert first(fields(fixed[5][0]),1)==first(fields(initial[5][0]),1)
    replay,_=req(valid,b'committed');assert replay==result
    # Full durability costs zero; the server never turns negative wear into money.
    _,full=req(repair('full',fixed),b'committed');assert first(full,4)==56
    move=integer(1,1)+blob(2,'move-after-repair')+integer(3,first(full,1))+integer(5,4)+integer(6,first(fields(full[5][0]),1))
    _,moved=req(move,b'committed')
    replay,_=req(valid,b'committed');assert replay==result
    _,latest=req();assert latest==moved
    _,other=req(actor=companion);damage(sql,'Companion',other)
    companion.logout();p.logout();restart();p=connect('explorer')
    _,saved=req();assert saved==moved
    replay,_=req(valid,b'committed');assert replay==result
    p.logout()
    print('PASS repair cost 44 from binary curve, insufficient money, unrepairable/spoofed item, atomic rollback, preserved instance, original retries and hard restart',flush=True)
