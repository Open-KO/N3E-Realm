"""Original friend fixtures: base game and item-equipped game share engine binaries."""
import json,shutil,sys
from pathlib import Path
from isolation import once_per_run

@once_per_run
def prepare(full=False,alternate=False):
    if full:
        from storage_auth_live import prepare as base
        base();source=Path('build/ko-completion/storage-auth/source')
    else:source=Path('games/demo')
    variant=('full'if full else'base')+('-alternate'if alternate else'')
    root=Path('build/ko-completion/friends')/variant/'source';root.mkdir(parents=True,exist_ok=True);shutil.copytree(source,root,dirs_exist_ok=True)
    m=json.loads((root/'package.json').read_text());m['engine_version']=23;m['protocol_version']=16
    m['friends']={'capacity':24,'name_bytes':20,'refresh_ticks':60}
    if alternate:
        m=json.loads(json.dumps(m).replace('demo:','alternate:').replace('"game_id": "demo"','"game_id": "alternate"'));m['friends']['capacity']=8
    (root/'package.json').write_text(json.dumps(m));sys.path.insert(0,str(Path('tools/assetc').resolve()));import main
    out=root.parent/'package';main.cook(root,out);return out.resolve()

def audit(connect,restart,sql,full=False):
    import time
    from world_peer import DISCONNECTED,fields,first,integer,blob
    from timescale import ticks
    # The presence refresh throttle is refresh_ticks=60; waits are 62 ticks (3.1 s
    # at the production 50 ms tick), so they follow a scaled run's tick (PQ-115).
    refresh=ticks(62)
    a=connect('explorer');b=connect('companion');state=None;seq=0
    def wait(p,tag):
        end=time.monotonic()+5
        while time.monotonic()<end:
            t,d=p.receive()
            if t==tag:return d
            assert t!=4,(t,d)
        raise AssertionError(('friend response deadline',tag))
    def request(op=0,name='',id=None,expected=None,status=b'ok',peer=None):
        nonlocal state,seq
        p=peer or a;seq+=1
        q=b''if op==0 else integer(1,op)+blob(2,id or 'friend-'+str(seq))+integer(3,first(state,3)if expected is None else expected)+blob(4,name)
        p.send(38,q);reply=wait(p,39);assert first(reply,2)==status,(reply,status)
        if peer is None and(state is None or first(reply,3)>=first(state,3)):state=reply
        return q,reply
    def names(s):return [first(fields(e),3)for e in s.get(5,[])]
    request();assert not names(state);request(peer=b)
    if not full:
        # Newer wire versions do not imply the presence of item capabilities.
        for tag in (32,34,36):
            a.send(tag,b'');error=wait(a,4);assert first(error,1)==5,error
        request()
    q,added=request(1,'companion',status=b'committed');assert names(state)==[b'Companion']
    assert not names(request(peer=b)[1])
    def presence(n,names):
        a.send(40,integer(1,n)+b''.join(blob(2,v)for v in names));return wait(a,41)
    observed=presence(1,['Companion','Missing','Explorer']);entries=[fields(e)for e in observed[3]]
    assert [first(e,4)for e in entries]==[1,0,1]and first(entries[0],3)==b.id and all(not first(e,5)for e in entries)
    a.send(40,integer(1,2)+blob(2,'Companion'));error=wait(a,4);assert first(error,2)==b'friend presence bounds/rate'
    b.logout();a.send(38,q);assert wait(a,39)==added
    request(1,'Companion',status=b'unavailable');a.pump(refresh);observed=presence(3,['Companion']);assert not first(fields(observed[3][0]),4)
    request(2,'companion',status=b'committed');assert not names(state)
    # Presence includes a logged-in dead target; add eligibility still rejects it.
    sql("UPDATE characters SET dead=true,life_revision=life_revision+1,respawn_ready_at=clock_timestamp() WHERE name='Companion' AND NOT online")
    b=connect('companion');request(1,'Companion',status=b'unavailable')
    # Keep both peers active while waiting out the presence refresh interval.
    until=time.monotonic()+refresh
    while time.monotonic()<until:a.pump(.1);b.pump(.1)
    observed=presence(4,['Companion']);assert first(fields(observed[3][0]),4)==1
    b.logout()
    longest='AbsentName1234567890';assert len(longest)==20
    a.pump(refresh);observed=presence(5,[longest]*24)
    assert len(observed[3])==24 and all(not first(fields(e),4)for e in observed[3])
    for n,names_ in [(6,['Missing']*25),(7,['NameIsOverTwentyBytesLong'])]:
        a.send(40,integer(1,n)+b''.join(blob(2,v)for v in names_));assert first(wait(a,4),2)==b'friend presence bounds/rate'
    sql("UPDATE characters SET dead=false,life_revision=life_revision+1,respawn_ready_at=NULL WHERE name='Companion' AND NOT online")
    b=connect('companion');request(1,'Companion',status=b'committed');b.logout();a.logout()
    for phase in ['before_commit','after_commit']:
        a=connect('explorer');request();before=first(state,3);count=int(sql('SELECT count(*) FROM friend_operations'))
        operation=integer(1,2)+blob(2,'crash-'+phase)+integer(3,before)+blob(4,'Companion');a.logout();restart(friend_fault=phase);a=connect('explorer');a.send(38,operation)
        deadline=time.monotonic()+6;closed=False
        try:
            while time.monotonic()<deadline:
                t,d=a.receive();assert t not in(4,39),('unexpected precrash result',phase,t,d)
        except DISCONNECTED:closed=True  # not a timeout (PQ-126)
        assert closed,'friend fault not reached';restart(expected_exit=97);a=connect('explorer');request()
        delta=int(phase=='after_commit');assert first(state,3)==before+delta and (b'Companion'in names(state))==(delta==0)
        assert int(sql('SELECT count(*) FROM friend_operations'))==count+delta
        a.send(38,operation);result=wait(a,39);assert first(result,2)==b'committed'and first(result,3)==before+1 and not names(result);state=result
        assert int(sql('SELECT count(*) FROM friend_operations'))==count+1
        if phase=='before_commit':b=connect('companion');request(1,'Companion',status=b'committed');b.logout()
        a.logout()
    print('PASS TLS directed friends, live/dead/missing/offline presence, maximum and excessive query bounds, refresh throttle, dead target denial, immutable retry, offline removal and both real commit crashes',flush=True)
