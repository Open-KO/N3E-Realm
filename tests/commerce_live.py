"""Real merchant transactions, authority and durable money/item conservation."""
import json,shutil,sys,time,math
from pathlib import Path
from world_peer import integer,blob,first,fields
from isolation import once_per_run

@once_per_run
def prepare():
    from inventory_live import prepare as bag_prepare
    bag_prepare();root=Path('build/ko-completion/commerce/source');root.mkdir(parents=True,exist_ok=True)
    shutil.copytree('build/ko-completion/items/source',root,dirs_exist_ok=True)
    m=json.loads((root/'package.json').read_text());m['engine_version']=16;m['protocol_version']=9
    m['inventory']['currency_limit']=100
    m['commerce']={'weight_limit':36,'max_quantity':9998,'bulk_price':100000,'bulk_quantity':10,
      'items':[{'id':'demo:item/token','weight':0,'price':1,'sell_divisor':6},{'id':'demo:item/blade','weight':20,'price':130,'sell_divisor':6},{'id':'demo:item/potion','weight':2,'price':13,'sell_divisor':6}],
      'shops':[{'id':'demo:shop/supplies','label':'Supplies','position':[0,0,0],'radius':3,'remote_sell':True,'items':['demo:item/blade','demo:item/potion']},
               {'id':'demo:shop/remote','label':'Distant shop','position':[20,0,20],'radius':3,'remote_sell':False,'items':['demo:item/potion']}]}
    (root/'package.json').write_text(json.dumps(m));sys.path.insert(0,str(Path('tools/assetc').resolve()));import main
    package=Path('build/ko-completion/commerce/package');main.cook(root,package);return package.resolve()

def audit(connect,restart,sql):
    p=connect('explorer');peer=connect('companion')
    def req(q=b'',status=b'ok',actor=None):
        a=actor or p;a.send(32,q);tag,r=a.until(33,4)
        assert tag==33 and first(r,2)==status,(tag,r,status)
        return r,fields(first(r,3))
    def slots(s):return [fields(v) for v in s[5]]
    def tx(id,s,op,slot,item,qty=1,service='demo:shop/supplies'):
        return integer(1,op)+blob(2,id)+integer(3,first(s,1))+integer(4,slot)+integer(6,first(slots(s)[slot],1))+blob(7,service)+blob(8,item)+integer(9,qty)
    _,initial=req();_,other=req(actor=peer)
    q=tx('ceiling',initial,3,1,'demo:item/potion');_,same=req(q,b'currency_limit');assert same==initial
    buy=tx('buy-1',initial,2,2,'demo:item/potion',3);original,s=req(buy,b'committed')
    assert first(s,4)==61 and first(slots(s)[2],3)==3 and first(slots(s)[2],1)>0
    bought=slots(s)[2];r,_=req(buy,b'committed');assert r==original
    _,same=req(tx('overweight',s,2,1,'demo:item/potion'),b'weight_limit');assert same==s
    _,same=req(tx('expensive',s,2,3,'demo:item/blade'),b'insufficient_currency');assert same==s
    _,same=req(tx('occupied',s,2,0,'demo:item/potion'),b'occupied_slot');assert same==s
    time.sleep(1.05)
    _,s=req(tx('sell-1',s,3,1,'demo:item/potion'),b'committed');assert first(s,4)==63
    serial=first(slots(s)[1],1)
    _,s=req(tx('merge-buy',s,2,1,'demo:item/potion'),b'committed')
    assert first(slots(s)[1],1)==serial and first(slots(s)[1],3)==5 and first(s,4)==50
    _,same=req(tx('oversell',s,3,2,'demo:item/potion',4),b'insufficient_items');assert same==s
    sell=tx('sell-stack',s,3,2,'demo:item/potion',3)
    # Fail exactly after the item/balance UPDATE: both must roll back.
    sql("CREATE FUNCTION fail_shop() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'test commerce rollback'; END $$; CREATE TRIGGER fail_shop BEFORE INSERT ON bag_operations FOR EACH ROW EXECUTE FUNCTION fail_shop()")
    p.send(32,sell);assert first(p.until(4)[1],1)==4
    sql('DROP TRIGGER fail_shop ON bag_operations; DROP FUNCTION fail_shop()')
    _,same=req();assert same==s
    _,s=req(sell,b'committed');assert not slots(s)[2] and first(s,4)==56
    _,unchanged=req(actor=peer);assert unchanged==other
    _,peer_bag=req(tx('round-buy',other,2,1,'demo:item/potion',3),b'committed',peer)
    _,peer_bag=req(tx('round-sell',peer_bag,3,1,'demo:item/potion',6),b'committed',peer)
    assert first(peer_bag,4)==74  # floor(13*6/6), not floor(13/6)*6.

    print('PASS merchant debit/credit, stack merge/emptying, instance preservation, capacity/weight/money bounds, original retries and atomic rollback',flush=True)
    time.sleep(1.05)
    for q in [tx('far',s,2,2,'demo:item/potion',service='demo:shop/remote'),tx('reward',s,2,2,'demo:item/token'),tx('unknown',s,2,2,'demo:item/unknown')]:
        p.send(32,q);assert first(p.until(4)[1],1)==4
    # Player coordinates in unknown fields cannot forge simulation admission.
    q=tx('forged-position',s,2,2,'demo:item/potion',service='demo:shop/remote')+integer(100,20)
    p.send(32,q);assert first(p.until(4)[1],1)==4
    end=time.monotonic()+10
    while time.monotonic()<end:
        p.pump(.05);peer.pump(.01);e=p.entities[p.id];x,z=first(e,3,0.),first(e,5,0.);d=math.hypot(x,8-z)
        if d<.3:break
        p.move(-x/d,(8-z)/d,mode=1)
    else:raise AssertionError('merchant range travel')
    p.move(0,0)
    p.send(32,tx('distant-buy',s,2,2,'demo:item/potion'));assert first(p.until(4)[1],1)==4
    _,s=req(tx('remote-sell',s,3,1,'demo:item/potion'),b'committed');assert first(s,4)==58
    print('PASS simulation-owned merchant range, forged position/offer rejection and package-selected remote sale behavior',flush=True)
    peer.logout();p.logout();restart();p=connect('explorer')
    _,saved=req();assert saved==s
    retry,_=req(buy,b'committed');assert retry==original
    # Remote retry of a sale remains exactly its original transaction result.
    _,same=req(tx('ceiling',initial,3,1,'demo:item/potion'),b'currency_limit');assert same==initial
    _,latest=req();assert latest==s
    print('PASS item and currency balance survive hard restart without duplicate purchases or sales',flush=True)
    p.logout()
