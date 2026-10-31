"""Original protected-warehouse fixture; no imported account records or credentials."""
import json,shutil,sys
from pathlib import Path
from isolation import once_per_run

@once_per_run
def prepare():
    from storage_live import prepare as base
    base();root=Path('build/ko-completion/storage-auth/source');root.mkdir(parents=True,exist_ok=True)
    shutil.copytree('build/ko-completion/storage/source',root,dirs_exist_ok=True)
    m=json.loads((root/'package.json').read_text());m['engine_version']=22;m['protocol_version']=15
    # Printable legacy-validator alphabet (regional password branch); configured original forbidden word.
    m['storage_auth']={'minimum':6,'maximum':16,'comparison':'ascii-insensitive','alphabet':'0123456789:;ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyz','forbidden':['SyntheticDenied']}
    (root/'package.json').write_text(json.dumps(m));sys.path.insert(0,str(Path('tools/assetc').resolve()));import main
    package=Path('build/ko-completion/storage-auth/package');main.cook(root,package);return package.resolve()

def audit(connect,restart,sql):
    import time
    from world_peer import DISCONNECTED,fields,first,integer,blob
    p=connect('explorer');bag=None;worlds=0
    def recv():
        nonlocal bag,worlds
        tag,data=p.receive()
        if tag==10:worlds+=1
        if tag==33:bag=fields(first(data,3))
        if tag==35 and 3 in data:bag=fields(first(data,3))
        return tag,data
    def auth(q,status):
        p.send(36,q);deadline=time.monotonic()+6
        while time.monotonic()<deadline:
            tag,data=recv()
            if tag==37:assert first(data,2)==status,(data,status);return data
            assert tag!=4,(tag,data)
        raise AssertionError("credential response deadline")
    def credential(op,name,old,new=''):
        return integer(1,op)+blob(2,name)+blob(3,'demo:bank/test')+blob(4,old)+(blob(5,new)if new else b'')
    def bank(name,status):
        p.send(32,b'')
        while recv()[0]!=33:pass
        q=blob(2,name)+blob(5,'demo:bank/test')+integer(3,first(bag,1))
        p.send(34,q);deadline=time.monotonic()+6
        while time.monotonic()<deadline:
            tag,data=recv()
            if tag==35:assert first(data,2)==status,(data,status);return data
            assert tag!=4,(tag,data)
        raise AssertionError("storage response deadline")
    assert first(auth(b'',b'locked'),4)==0
    locked=bank('locked',b'locked');assert 3 not in locked and 4 not in locked
    auth(credential(1,'bad','Incorrect_123'),b'invalid_credentials')
    unlock=credential(1,'unlock','oRiGiNaL_123');before=worlds
    original=auth(unlock,b'unlocked');assert first(original,4)==1 and worlds-before>=2,('ticks during hashing',worlds-before)
    assert auth(unlock,b'unlocked')==original
    opening=bank('opened',b'committed');assert len(fields(first(opening,4))[4])==192
    change=credential(2,'change','ORIGINAL_123','Replacement_123');changed=auth(change,b'changed');assert first(changed,4)==2
    assert auth(change,b'changed')==changed
    p.logout();p=connect('explorer');assert first(auth(b'',b'locked'),4)==0
    bank('opened',b'locked');historical=auth(unlock,b'unlocked');assert first(historical,3)==1 and first(historical,4)==0
    secret='Replacement_123'
    for i,phase in enumerate(['before_commit','after_commit']):
        revision=int(sql('SELECT revision FROM storage_credentials c JOIN accounts a ON a.id=c.account_id WHERE a.name=\'explorer\''))
        count=int(sql('SELECT count(*) FROM storage_credential_operations'));new='Crash_'+str(i)+'_123'
        request=credential(2,'crash-'+phase,secret,new);p.logout();restart(storage_auth_fault=phase);p=connect('explorer');p.send(36,request)
        try:
            deadline=time.monotonic()+6
            while time.monotonic()<deadline:
                tag,data=recv();assert tag not in(4,37),('unexpected pre-crash result',phase,data)
        except DISCONNECTED:pass  # not a timeout (PQ-126); restart() checks exit 96
        restart(expected_exit=96);p=connect('explorer')
        delta=int(phase=='after_commit');assert int(sql('SELECT revision FROM storage_credentials c JOIN accounts a ON a.id=c.account_id WHERE a.name=\'explorer\''))==revision+delta
        assert int(sql('SELECT count(*) FROM storage_credential_operations'))==count+delta
        result=auth(request,b'changed');assert first(result,3)==revision+1 and first(result,4)==revision+1
        assert int(sql('SELECT count(*) FROM storage_credential_operations'))==count+1;secret=new
    # Ten password attempts have exhausted this account's shared minute budget.
    p.send(36,credential(1,'limited',secret))
    while True:
        tag,data=recv()
        if tag==4:assert first(data,2)==b'storage password rate limit',data;break
        assert tag!=37,('missing credential throttle',data)
    # Read-only status and movement remain available while password attempts are limited.
    assert first(auth(b'',b'unlocked'),4)==4;p.pump(.2)
    rows=sql('SELECT row_to_json(c) FROM storage_credential_operations c')
    for secret in ['Original_123','Incorrect_123','Replacement_123','Crash_0_123','Crash_1_123']:assert secret not in rows
    p.logout()
    print('PASS TLS warehouse password prompts, locked/replayed storage denial, ticks during hashing, logout invalidation, both real commit crashes, exact retry, rate limit and no plaintext ledger',flush=True)
