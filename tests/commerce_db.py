"""Isolated PostgreSQL merchant concurrency and admission fences."""
import os
from pathlib import Path
import subprocess
import time
import uuid
from commerce_live import prepare
from readiness import wait_postgres
from isolation import DISPOSABLE_POSTGRES, container_logs
package=prepare()
B=Path('build/ko-completion/commerce');B.mkdir(parents=True,exist_ok=True)
name='n3e-commerce-'+uuid.uuid4().hex[:10]
def run(*args,good=True,env=None):
    p=subprocess.run(args,capture_output=True,text=True,env=env,timeout=180)
    assert not good or p.returncode==0,(args,p.stdout,p.stderr)
    return p
try:
    run('docker','run','-d','--rm','--name',name,'-e','POSTGRES_USER=n3e','-e','POSTGRES_PASSWORD=test-only','-e','POSTGRES_DB=n3e',*DISPOSABLE_POSTGRES,'-p','127.0.0.1::5432','postgres:17.4-bookworm@sha256:304ab813518754228f9f792f79d6da36359b82d8ecf418096c636725f8c930ad')
    port=wait_postgres(name)
    env={**os.environ,'N3E_PACKAGE':str(package),'N3E_TEST_DATABASE_URL':f'host=127.0.0.1 port={port} user=n3e password=test-only dbname=n3e'}
    p=run('cargo','test','--locked','commerce::tests::durable_authority','--','--ignored','--exact','--nocapture',env=env,good=False)
    (B/'database.log').write_text(p.stdout+p.stderr)
    assert p.returncode==0,(p.stdout,p.stderr)
    print(p.stdout)
finally:
    container_logs('postgres',['docker','logs','--timestamps',name])  # PQ-128: before the container is removed
    run('docker','rm','-f',name,good=False)
