"""Original item fixture and real TLS persistence/authority/retry checks."""
import json
import shutil
import sys
import time
from pathlib import Path
from world_peer import blob, integer, first, fields
from isolation import once_per_run


@once_per_run
def prepare():
    sys.path.insert(0,str(Path('tools/assetc').resolve()))
    import main
    root=Path('build/ko-completion/items/source'); root.mkdir(parents=True,exist_ok=True)
    shutil.copytree('games/demo',root,dirs_exist_ok=True)
    m=json.loads((root/'package.json').read_text()); m['engine_version']=15; m['protocol_version']=8
    m['inventory']={'capacity':12,'currency':'demo:currency/coin','currency_limit':1000000000,'starting_currency':100,'items':[
        {'id':m['gameplay']['item'],'label':'Token','stack_limit':1,'durability':0,'starting':0},
        {'id':'demo:item/blade','label':'Practice blade','stack_limit':1,'durability':80,'starting':1},
        {'id':'demo:item/potion','label':'Practice potion','stack_limit':20,'durability':0,'starting':5}]}
    (root/'package.json').write_text(json.dumps(m)); package=Path('build/ko-completion/items/package'); main.cook(root,package)
    return package.resolve()


def audit(connect, restart, sql):
    p=connect('explorer',select=False); p.send(32)
    assert first(p.until(4)[1],1)==5; p.logout()
    p=connect('explorer'); other=connect('companion')
    def request(peer,payload=b'',status=b'ok'):
        peer.send(32,payload); tag,r=peer.until(33,4)
        assert tag==33 and first(r,2)==status,(tag,r,status)
        return r,fields(first(r,3))
    def slots(state): return [fields(s) for s in state[5]]
    def swap(name,state,src,dst,instance=None):
        return integer(1,1)+blob(2,name)+integer(3,first(state,1))+integer(4,src)+integer(5,dst)+integer(6,first(slots(state)[src],1) if instance is None else instance)
    _,initial=request(p); items=slots(initial)
    assert first(initial,2)==12 and first(initial,3)==b'demo:currency/coin' and first(initial,4)==100
    assert first(items[0],2)==b'demo:item/blade' and first(items[0],4)==80
    assert first(items[1],2)==b'demo:item/potion' and first(items[1],3)==5
    _,foreign=request(other)
    forged=swap('foreign',initial,0,2,first(slots(foreign)[0],1))
    _,unchanged=request(p,forged,b'instance_conflict'); assert unchanged==initial
    q=swap('move-1',initial,0,1)
    original,one=request(p,q,b'committed')
    assert first(one,1)==1 and slots(one)[0]==items[1] and slots(one)[1]==items[0]
    retry,_=request(p,q,b'committed'); assert retry==original
    _,same=request(p,swap('stale',initial,0,2),b'revision_conflict'); assert same==one
    _,two=request(p,swap('move-2',one,1,8),b'committed')
    assert slots(two)[8]==items[0] and not slots(two)[1]
    retry,_=request(p,q,b'committed'); assert retry==original
    _,latest=request(p); assert latest==two
    # A request ID cannot authorize a different move, even when old result exists.
    _,same=request(p,swap('move-1',two,0,4),b'request_conflict'); assert same==two
    time.sleep(1.05)
    _,same=request(p,swap('outside',two,0,64),b'invalid_slot'); assert same==two
    _,foreign_after=request(other); assert foreign_after==foreign
    # Fail after UPDATE but before the result ledger insert: the whole move rolls back.
    sql("CREATE FUNCTION reject_test_bag() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'test rollback'; END $$; CREATE TRIGGER test_bag BEFORE INSERT ON bag_operations FOR EACH ROW EXECUTE FUNCTION reject_test_bag()")
    failed=swap('rollback',two,0,3); p.send(32,failed)
    assert first(p.until(4)[1],1)==4
    sql('DROP TRIGGER test_bag ON bag_operations; DROP FUNCTION reject_test_bag()')
    _,latest=request(p); assert latest==two
    _,three=request(p,failed,b'committed'); assert slots(three)[3]==items[1]
    assert sql("SELECT count(*) FROM bag_operations WHERE request='rollback'").strip()=='1'
    print('PASS authenticated item identities, whole-record swaps, revisions, duplicate/conflicting retries, other-character isolation and transaction rollback',flush=True)
    p.logout(); other.logout(); p=connect('explorer')
    _,saved=request(p); assert saved==three
    retry,_=request(p,q,b'committed'); assert retry==original
    restart(); p=connect('explorer')
    _,saved=request(p); assert saved==three
    retry,_=request(p,q,b'committed'); assert retry==original
    print('PASS acknowledged bag state and original retry outcomes survive logout and SIGKILL/restart',flush=True)
    p.logout()
    restart(compatibility=True)
