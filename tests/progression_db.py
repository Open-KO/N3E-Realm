"""Disposable real Postgres contract/fault suite, backup and forward migration checks."""
import hashlib
import os
from pathlib import Path
import subprocess
import time
import uuid
from readiness import wait_postgres
from isolation import DISPOSABLE_POSTGRES, container_logs
from schema_states import ahead_of_server, migrate_to

# 001-004 as deployed before progression: a shipped migration never changes, or every
# database migrated by an older release fails `migration checksum mismatch`.
SHIPPED=['d2320c95062848b889a09ebf6cbbdc914a47493a262ebaac037df2551acffdcf','7eef043cabf88105f4902f3cc8a287bb8d8499bd133b0e154d2a38064aad5cd3',
         'ff47db58aa8c57c9eca71704f26f7041352bdfe1c3d7d6da7a9182fcf69dc595','ed563b5a92794fef3456d44d4597a2b8f058e5fa5d6b4f6653b7bf570dd02fef']

ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)
B=ROOT/'build/ko-09';B.mkdir(parents=True,exist_ok=True)
name='n3e-ko09-'+uuid.uuid4().hex[:10]
image='postgres:17.4-bookworm@sha256:304ab813518754228f9f792f79d6da36359b82d8ecf418096c636725f8c930ad'

def run(*cmd,env=None,good=True,stdin=None):
    p=subprocess.run(cmd,env=env,input=stdin,capture_output=True,timeout=300)
    if good and p.returncode: raise AssertionError((cmd,p.returncode,p.stdout.decode(),p.stderr.decode()))
    return p

def sql(q):
    return run('docker','exec',name,'psql','-U','n3e','-d','n3e','-Atc',q).stdout.decode().strip()

try:
    run('docker','run','-d','--rm','--name',name,'-e','POSTGRES_USER=n3e','-e','POSTGRES_PASSWORD=test-only','-e','POSTGRES_DB=n3e',*DISPOSABLE_POSTGRES,'-p','127.0.0.1::5432',image)
    port=wait_postgres(name)
    env={**os.environ,'N3E_TEST_DATABASE_URL':f'host=127.0.0.1 port={port} user=n3e password=test-only dbname=n3e'}
    # Establish the pre-progression schema (001-004) as its release's migrate left it (Q28).
    migrate_to(name,4)
    db_env={**env,'DATABASE_URL':env['N3E_TEST_DATABASE_URL']}
    before=sql('SELECT version,digest FROM schema_migrations ORDER BY version')
    assert before=='\n'.join(f'{v}|{d}' for v,d in enumerate(SHIPPED,1)),before
    sql("INSERT INTO realm_ownership VALUES('test-legacy-backup','offline',1,clock_timestamp()); INSERT INTO accounts(name,salt,password_hash) VALUES('legacy-backup',decode(repeat('00',16),'hex'),decode(repeat('00',32),'hex')); INSERT INTO characters(account_id,realm,name,dead,respawn_ready_at,life_revision) SELECT id,'test-legacy-backup','Saved',true,clock_timestamp(),3 FROM accounts WHERE name='legacy-backup'; INSERT INTO character_progress SELECT id,'demo:item/token',2,8,45 FROM characters WHERE realm='test-legacy-backup'; INSERT INTO character_roles SELECT id,realm,'demo','world.edit' FROM characters WHERE realm='test-legacy-backup'; INSERT INTO reward_operations(operation,character_id,realm,item,quantity,xp_grant,status,result_count,result_xp) SELECT nextval('entity_instances'),id,realm,'demo:item/token',1,10,'inventory_full',2,45 FROM characters WHERE realm='test-legacy-backup'")
    backup=run('docker','exec',name,'pg_dump','-U','n3e','-d','n3e','--no-owner').stdout
    (B/'pre-conversion.sql').write_bytes(backup)
    run('cargo','build','--locked')
    p=run('cargo','test','--locked','settlements::tests::real_database_contract','--','--ignored','--exact','--nocapture',env=env)
    (B/'database.log').write_bytes(p.stdout+p.stderr)
    print(p.stdout.decode())
    assert sql('SELECT version,digest FROM schema_migrations WHERE version<=4 ORDER BY version')==before
    # A server behind the database's schema refuses readiness; the synthetic row is then dropped.
    server=ahead_of_server(name)
    old_check=run(str(server),'account-create','old-check',env=db_env,stdin=b'test-only-password\n',good=False)
    assert old_check.returncode!=0 and b'migration version mismatch' in old_check.stderr, old_check.stderr
    sql("DELETE FROM schema_migrations WHERE digest='synthetic-future'")
    dump=run('docker','exec',name,'pg_dump','-U','n3e','-d','n3e','--no-owner').stdout
    (B/'post-settlement.sql').write_bytes(dump)
    run('docker','exec',name,'createdb','-U','n3e','restore_check')
    run('docker','exec','-i',name,'psql','-v','ON_ERROR_STOP=1','-U','n3e','-d','restore_check',stdin=dump)
    query="SELECT md5(string_agg(row_to_json(t)::text,E'\\n' ORDER BY realm,encounter)) FROM encounter_settlements t"
    restored=run('docker','exec',name,'psql','-U','n3e','-d','restore_check','-Atc',query).stdout.decode().strip()
    assert restored==sql(query)
    for table,order in [('character_progress','character_id'),('character_reward_progress','character_id'),('encounter_recipients','realm,encounter,character_id'),('loot_entitlements','realm,encounter'),('reward_operations','operation'),('characters','id')]:
        q=f"SELECT md5(string_agg(row_to_json(t)::text,E'\\n' ORDER BY {order})) FROM {table} t"
        assert run('docker','exec',name,'psql','-U','n3e','-d','restore_check','-Atc',q).stdout.decode().strip()==sql(q)
    # Restore the pre-conversion backup, preserving the exact legacy schema.
    run('docker','exec',name,'createdb','-U','n3e','legacy_restore')
    run('docker','exec','-i',name,'psql','-v','ON_ERROR_STOP=1','-U','n3e','-d','legacy_restore',stdin=backup)
    assert run('docker','exec',name,'psql','-U','n3e','-d','legacy_restore','-Atc','SELECT version,digest FROM schema_migrations ORDER BY version').stdout.decode().strip()==before
    for table,key in [('characters','realm'),('character_roles','realm'),('reward_operations','realm')]:
        query=f"SELECT md5(string_agg(row_to_json(t)::text,E'\\n' ORDER BY row_to_json(t)::text)) FROM {table} t WHERE {key}='test-legacy-backup'"
        restored=run('docker','exec',name,'psql','-U','n3e','-d','legacy_restore','-Atc',query).stdout.decode().strip()
        assert restored==sql(query)
    query="SELECT row_to_json(p)::text FROM character_progress p JOIN characters c ON c.id=p.character_id WHERE realm='test-legacy-backup'"
    assert run('docker','exec',name,'psql','-U','n3e','-d','legacy_restore','-Atc',query).stdout.decode().strip()==sql(query)
    (B/'backup-sha256.txt').write_text(''.join(f'{hashlib.sha256(data).hexdigest()}  {file}\n' for file,data in [('pre-conversion.sql',backup),('post-settlement.sql',dump)]))
    print('001-004 checksums, behind-schema rejection, forward migration, post-settlement and legacy backup restore: pass')
finally:
    container_logs('postgres',['docker','logs','--timestamps',name])  # PQ-128: before the container is removed
    run('docker','rm','-f',name,good=False)
