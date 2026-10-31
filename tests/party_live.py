"""Original party fixture and authoritative live membership checks."""
import json,select,shutil,sys,time
from pathlib import Path
from isolation import once_per_run

@once_per_run
def prepare(full=False,alternate=False,friends=True):
    if friends or full:
        from friends_live import prepare as base
        source=base(full=full,alternate=alternate).parent/'source'
    else:source=Path('games/demo')
    variant=('full'if full else'base')+('-alternate'if alternate else'')+(''if friends else'-no-friends')
    root=Path('build/ko-completion/party')/variant/'source';root.mkdir(parents=True,exist_ok=True);shutil.copytree(source,root,dirs_exist_ok=True)
    m=json.loads((root/'package.json').read_text());m['engine_version']=24;m['protocol_version']=17
    m['party']={'capacity':4 if alternate else 8,'name_bytes':20,'level_minimum':2/3,'level_maximum':1.5,'level_gap':8,'repeat_ticks':60}
    if not friends:m.pop('friends',None)
    (root/'package.json').write_text(json.dumps(m));sys.path.insert(0,str(Path('tools/assetc').resolve()));import main
    out=root.parent/'package';main.cook(root,out);return out.resolve()

def audit(connect,restart,sql):
    from world_peer import fields,first,integer,blob
    peers={name:connect(name)for name in ('explorer','companion','bystander')};seq={};states={};pings={}
    def heartbeat():
        now=time.monotonic()
        for p in peers.values():
            if now-pings.get(p,0)>.5:p.send(14);pings[p]=now
    def pump(until):
        while time.monotonic()<until:
            for p in list(peers.values()):
                heartbeat()
                tag,data=p.receive()
                if tag==43:states[p]=data
                elif tag==4:raise AssertionError(data)
    def wait(p,tag):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            heartbeat()
            t,d=p.receive()
            if t==43:states[p]=d
            if t==tag:return d
            assert t!=4,(t,d)
        raise AssertionError(('party reply timeout',tag))
    def call(p,op=0,name='',token=0,status=b'ok'):
        seq[p]=seq.get(p,0)+1;q=integer(1,seq[p])+integer(2,op)+blob(3,name)+integer(4,token)
        p.send(42,q);r=wait(p,44);assert first(r,1)==seq[p]and first(r,2)==status,(r,status)
        return q
    def roster(p,count):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            s=wait(p,43)
            if len(s.get(4,[]))==count:return s
        raise AssertionError(('party roster',count,states.get(p)))
    def invited(p):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            s=wait(p,43)
            if first(s,5):return s
        raise AssertionError('party invite timeout')
    a,b,c=(peers[n]for n in ('explorer','companion','bystander'))
    for p in (a,b,c):call(p);roster(p,0)
    call(a,1,'companion',status=b'invited');s=invited(b);token=first(s,5);assert token and first(s,7)==b'Explorer'
    call(c,2,token=token,status=b'no_invitation');call(b,2,token=token+1,status=b'stale_invitation')
    call(b,2,token=token,status=b'joined');s=roster(b,2);leader=first(s,3);assert leader and all(first(fields(m),7)>0 for m in s[4])
    call(b,1,'Bystander',status=b'not_leader');call(b,5,status=b'not_leader');call(b,4,'Explorer',status=b'not_leader')
    call(a,1,'Bystander',status=b'invited');s=invited(c);token=first(s,5);assert token
    call(c,2,token=token,status=b'joined');roster(c,3)
    # Friend presence includes accepted parties; ownership of friend lists is independent.
    a.send(40,integer(1,1)+blob(2,'Companion'));presence=wait(a,41);assert first(fields(presence[3][0]),5)==1
    call(a,4,status=b'removed');call(b);s=roster(b,2);assert first(s,3)!=leader
    call(b,4,'Explorer',status=b'not_member')
    # Disconnecting the new leader dissolves the remaining two-person group.
    b.logout();del peers['companion'];roster(c,0);b=connect('companion');peers['companion']=b;call(b);roster(b,0)
    # Decline a singleton offer; repeating immediately is throttled and cannot revive it.
    call(c,1,'Companion',status=b'invited');token=first(invited(b),5);call(b,3,token=token,status=b'declined');roster(c,0)
    call(c,1,'Companion',status=b'rate_limited');call(b,2,token=token,status=b'no_invitation')
    # A stale sequence is rejected without changing membership.
    b.send(42,integer(1,seq[b])+integer(2,5));assert first(wait(b,4),2)==b'party request bounds/sequence'
    pump(time.monotonic()+3.2)
    call(c,1,'Companion',status=b'invited');token=first(invited(b),5)
    call(c,5,status=b'disbanded');call(b,2,token=token,status=b'no_invitation')
    # Kill the process with an accepted group AND an unanswered invitation alive.
    call(a,1,'Companion',status=b'invited');token=first(invited(b),5);call(b,2,token=token,status=b'joined');roster(b,2)
    call(a,1,'Bystander',status=b'invited');old_token=first(invited(c),5)
    restart()
    for p in peers.values():p.s.close()
    peers.clear()
    for name in ('explorer','companion','bystander'):
        p=connect(name);peers[name]=p;call(p);roster(p,0)
    call(peers['bystander'],2,token=old_token,status=b'no_invitation')
    operator_visibility(peers,call,heartbeat,sql,invited)
    for p in peers.values():p.logout()
    peers.clear()
    print('PASS TLS party invitation consent, forged tokens, leader authority, live roster/vitals, friend party presence, leadership transfer, disconnect/reconnect, decline, rate/sequence bounds and process restart',flush=True)

def operator_visibility(peers,call,heartbeat,sql,invited):
    """PQ-184 (D-152): a server.inspect holder is withheld from the sessions whose
    own server.inspect lease is not current. The name lookups checked here answer
    as for a character that is not online: a party invitation is unavailable, friend
    presence reports it offline with no character or entity, and a friend
    addition finds no one. The grant and revoke are the character_roles row the
    simulation's authority read finds (what `n3e-server role` writes)."""
    from world_peer import fields,first,integer,blob
    a,b,c=(peers[n]for n in ('explorer','companion','bystander'))
    def grant(name,on=True):
        sql(("INSERT INTO character_roles SELECT id,realm,'*','server.inspect' FROM characters WHERE name='%s' ON CONFLICT DO NOTHING" if on else "DELETE FROM character_roles WHERE capability='server.inspect' AND character_id=(SELECT id FROM characters WHERE name='%s')")%name)
    def reply(p,tag):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            heartbeat();t,d=p.receive()
            if t==tag:return d
            assert t!=4,(t,d)
        raise AssertionError(('reply timeout',tag))
    def views(seconds):
        """Entity ids each peer's Worlds held, and every id they named (entities,
        strike and cast targets, presentation actors and targets). Each peer is
        read until its socket is empty, so a backlog does not lag the window."""
        seen={p:[] for p in (a,b,c)};end=time.monotonic()+seconds
        while time.monotonic()<end:
            heartbeat()
            ready=[p for p in (a,b,c) if p.s.pending()] or select.select([p.s for p in (a,b,c)],[],[],.05)[0]
            for p in (a,b,c):
                if p not in ready and p.s not in ready:continue
                t,d=p.receive()
                assert t!=4,(t,d)
                if t!=10:continue
                es=[fields(e) for e in d.get(4,[])]
                named={first(e,1) for e in es}|{first(e,25) for e in es}|{first(e,29) for e in es}
                for v in d.get(14,[]):named|={first(fields(v),3),first(fields(v),4)}
                seen[p].append(({first(e,1) for e in es},named))
        return seen
    def holds(seen,p,q):return any(q.id in ids for ids,_ in seen[p])
    def never(seen,p,q):return bool(seen[p]) and all(q.id not in named for _,named in seen[p])
    def settle(condition,label):
        """Read until `condition` holds over a fresh 0.5 s window (the grant or
        revoke reaches the simulation at its next authority read), then return
        the next 1.5 s, over which the caller asserts."""
        deadline=time.monotonic()+8
        while not condition(views(.5)):
            assert time.monotonic()<deadline,label
        return views(1.5)
    seen=views(1.5)
    assert holds(seen,a,c) and holds(seen,b,c),'the bystander is not in view: the check proves nothing'
    grant('Bystander')
    seen=settle(lambda v:never(v,a,c) and never(v,b,c),'the holder was never withheld')
    assert never(seen,a,c) and never(seen,b,c),'a session without server.inspect received the holder'
    assert holds(seen,c,a) and holds(seen,c,b),'the holder does not see the players'
    call(a,1,'Bystander',status=b'unavailable')
    a.send(40,integer(1,1)+blob(2,'Bystander'));entry=fields(reply(a,41)[3][0])
    assert (first(entry,2),first(entry,3),first(entry,4))==(0,0,0),entry
    a.send(38,b'');revision=first(reply(a,39),3)
    a.send(38,integer(1,1)+blob(2,'pq184-add')+integer(3,revision)+blob(4,'Bystander'))
    assert first(reply(a,39),2)==b'unavailable'
    c.send(40,integer(1,1)+blob(2,'Explorer'));assert first(fields(reply(c,41)[3][0]),4)==1,'the holder cannot find a player'
    # A non-leader's removal by name answers for the hidden holder as for an
    # absent name (not_member), where a visible member (the leader) gets
    # not_leader (the unit test also covers a visible non-member).
    call(a,1,'Companion',status=b'invited');token=first(invited(b),5);call(b,2,token=token,status=b'joined')
    call(b,4,'Bystander',status=b'not_member');call(b,4,'Nobody',status=b'not_member');call(b,4,'Explorer',status=b'not_leader')
    call(a,5,status=b'disbanded')
    # A second holder sees the first; the first sees it.
    grant('Companion')
    seen=settle(lambda v:holds(v,b,c) and never(v,a,b),'the second holder never saw the first')
    assert holds(seen,b,c) and holds(seen,c,b) and never(seen,a,b) and never(seen,a,c),'holders do not see each other'
    grant('Companion',False);grant('Bystander',False)
    seen=settle(lambda v:holds(v,a,c) and holds(v,a,b),'a revocation did not show the operators again')
    assert holds(seen,a,c) and holds(seen,a,b) and holds(seen,b,c),'a revocation did not show the operators again'
    call(a,1,'Bystander',status=b'invited')
    print('PASS operator visibility: a server.inspect holder is withheld from World entities, targets and events of sessions without it, and is unavailable to their party invitation, a removal by name from a non-leader (not_member, as for an absent name), friend presence and friend addition; holders see each other; revocation shows them',flush=True)

def graphical_observer(p,client,on_join=None):
    from world_peer import first,integer,blob
    stage=seq=0;next_action=0;ping=0;end=time.monotonic()+(50 if on_join else 30)
    def send(op,token=0,name=''):
        nonlocal seq
        seq+=1;p.send(42,integer(1,seq)+integer(2,op)+blob(3,name)+integer(4,token))
    while client.poll()is None and time.monotonic()<end:
        now=time.monotonic()
        if now>=ping:p.send(14);ping=now+.5
        if stage in(3,6)and now>=next_action:send(1,name='Companion');stage+=1
        t,d=p.receive()
        assert t!=4,(t,d)
        if t==44:assert first(d,2)in(b'invited',b'joined'),d
        if t!=43:continue
        count=len(d.get(4,[]))
        if stage==0 and first(d,5):send(2,token=first(d,5));stage=1
        elif stage==1 and count==2:
            if on_join:on_join(p)
            stage=2
        elif stage==2 and not first(d,2):stage=3;next_action=time.monotonic()+.8
        elif stage==4 and count==1:stage=5
        elif stage==5 and not first(d,2):stage=6;next_action=time.monotonic()+3.2
    assert stage==7,('party graphical observer',stage)
