#!/usr/bin/env python3
"""Restore a user-supplied SQL Server backup into a disposable offline container.

Exports schema/counts only. Never imports accounts or state into the engine.
The backup, restored database and generated reports remain local.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import uuid

IMAGE = 'mcr.microsoft.com/mssql/server@sha256:4402d880dd4c34bfa7d8705e56a86cd6c88da80a1f6bbbe741f999e76264a090'
SQLCMD = '/opt/mssql-tools18/bin/sqlcmd'
# Explicit definition-only allowlist; account, user, coupon and credential tables
# are deliberately unavailable through row export. Metadata covers every table.
DEFINITION_TABLES = frozenset('''COEFFICIENT EVENT EVENT_TRIGGER HOME ITEM
ITEM_EXCHANGE ITEM_GROUP ITEM_UPGRADE ITEMUP_PROBABILITY K_MONSTER K_MONSTER_ITEM
K_NPC K_NPC_ITEM K_NPC_MOVE_ITEM K_NPCPOS KNIGHTS_CAPE LEVEL_UP MAGIC
MAGIC_TYPE1 MAGIC_TYPE2 MAGIC_TYPE3 MAGIC_TYPE4 MAGIC_TYPE5 MAGIC_TYPE6 MAGIC_TYPE7
MAGIC_TYPE8 MAGIC_TYPE9 MAKE_DEFENSIVE MAKE_ITEM MAKE_ITEM_GRADECODE MAKE_ITEM_GROUP
MAKE_ITEM_LARECODE MAKE_WEAPON MONSTER_CHALLENGE MONSTER_CHALLENGE_SUMMON_LIST
MONSTER_SUMMON_LIST SERVER_RESOURCE START_POSITION VERSION ZONE_INFO'''.split())
# Stored-procedure text that the supplied executables call by name. Exported as
# text for static comparison only; nothing is ever executed. Every procedure
# name is listed (metadata only) so this allowlist can be reviewed.
PROCEDURES = frozenset('''ACCOUNT_LOGIN ACCOUNT_LOGOUT LOAD_USER_DATA UPDATE_USER_DATA
LOAD_CHAR_INFO LOAD_ACCOUNT_CHARID CREATE_NEW_CHAR DELETE_CHAR NATION_SELECT
LOAD_KNIGHTS_MEMBERS UPDATE_KNIGHTS_WAR LOAD_SAVED_MAGIC UPDATE_SAVED_MAGIC
CLEAR_REMAIN_USERS RESET_LOYALTY_MONTHLY RANK_KNIGHTS UPDATE_PERSONAL_RANK
KNIGHTS_RATING_UPDATE USER_KNIGHTS_RATING_UPDATE CLAIM_USER_RANK_STIPEND'''.split())


def run(args, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, timeout=180, **kwargs)
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed ({result.returncode}): {result.stderr or result.stdout}')
    return result.stdout


def inspect(backup, output, definitions=(), procedure_names=()):
    if not set(definitions) <= DEFINITION_TABLES:
        raise ValueError("row export is restricted to definition tables")
    if not set(procedure_names) <= PROCEDURES:
        raise ValueError("procedure export is restricted to the procedure allowlist")
    backup = backup.resolve(strict=True)
    output.mkdir(parents=True, exist_ok=True)
    output = output.resolve()
    name = 'n3e-ko-reference-' + uuid.uuid4().hex[:12]
    envfile = output / (name + '.env')
    fd = os.open(envfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write('ACCEPT_EULA=Y\nMSSQL_PID=Developer\nMSSQL_MEMORY_LIMIT_MB=2048\nMSSQL_SA_PASSWORD=' + secrets.token_urlsafe(32) + 'aA1!\n')

    def sql(query):
        # Password expands only inside the container, never in argv or output.
        return run(['docker', 'exec', '-i', name, 'sh', '-c',
                    'SQLCMDPASSWORD="$MSSQL_SA_PASSWORD" exec ' + SQLCMD +
                    ' -S 127.0.0.1 -U sa -C -b -l 3 -t 120 -m1 -h-1 -y8000 -w65535 -Q "$1"', 'sqlcmd', 'SET NOCOUNT ON; ' + query])

    def json_query(query):
        # sqlcmd can pad/wrap text at arbitrary chunk boundaries, including
        # inside JSON strings. Transport UTF-16 bytes as bounded hex rows and
        # verify the server-side digest before parsing; never strip JSON text.
        prefix = 'USE [ko_reference]; '
        if not query.startswith(prefix):
            raise ValueError('reference query database')
        select = query[len(prefix):]
        encoded = prefix + "DECLARE @payload nvarchar(max)=COALESCE((" + select + " FOR JSON PATH),N'[]'); "
        encoded += "IF DATALENGTH(@payload)>134217728 THROW 50000, 'reference JSON bound', 1; "
        encoded += "SELECT 'SHA256:' + CONVERT(varchar(64),HASHBYTES('SHA2_256',@payload),2); "
        encoded += ";WITH chunks AS (SELECT 1 AS n UNION ALL SELECT n+1000 FROM chunks WHERE n+1000<=DATALENGTH(@payload)/2) "
        encoded += "SELECT CONVERT(varchar(4000),CONVERT(varbinary(2000),SUBSTRING(@payload COLLATE Latin1_General_100_BIN2,n,1000)),2) FROM chunks ORDER BY n OPTION(MAXRECURSION 0);"
        lines = [line.strip() for line in sql(encoded).splitlines() if line.strip()]
        if not lines or not lines[0].startswith('SHA256:'):
            raise RuntimeError('reference JSON digest missing')
        data = bytes.fromhex(''.join(lines[1:]))
        if hashlib.sha256(data).hexdigest() != lines[0][7:].lower():
            raise RuntimeError('reference JSON transport digest mismatch')
        return json.loads(data.decode('utf-16-le'))

    created = False
    try:
        run(['docker', 'run', '--rm', '-d', '--name', name, '--network', 'none',
             '--memory', '3g', '--cpus', '2', '--env-file', str(envfile),
             '--mount', f'type=bind,source={backup},target=/reference.bak,readonly', IMAGE])
        created = True
        envfile.unlink()
        deadline = time.monotonic() + 90
        while True:
            try:
                sql('SELECT 1;')
                break
            except RuntimeError:
                if time.monotonic() > deadline:
                    raise RuntimeError('isolated SQL Server did not become ready') from None
                time.sleep(1)
        for operation in ['HEADERONLY', 'FILELISTONLY', 'VERIFYONLY']:
            (output / (operation.lower() + '.txt')).write_text(sql(f"RESTORE {operation} FROM DISK=N'/reference.bak';"))
        # Each file-list row starts with logical name, physical name and D/L.
        rows = [row.split() for row in (output / 'filelistonly.txt').read_text().splitlines() if row.strip()]
        moves = []
        for i, row in enumerate(rows):
            if len(row) < 3 or row[2] not in ('D', 'L'):
                raise RuntimeError('unsupported backup file-list format; inspect local report')
            logical = row[0].replace("'", "''")
            moves.append(f"MOVE N'{logical}' TO N'/var/opt/mssql/data/reference-{i}.{'ldf' if row[2] == 'L' else 'mdf'}'")
        if not moves:
            raise RuntimeError('backup contains no restorable files')
        restore = sql("RESTORE DATABASE [ko_reference] FROM DISK=N'/reference.bak' WITH " + ', '.join(moves) + '; ALTER DATABASE [ko_reference] SET READ_ONLY;')
        (output / 'restore.txt').write_text(restore)
        with backup.open('rb') as stream:
            backup_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
        identity = {'backup_name': backup.name, 'bytes': backup.stat().st_size,
                    'sha256': backup_hash,
                    'image': IMAGE, 'version': sql('SELECT @@VERSION;').strip()}
        (output / 'identity.json').write_text(json.dumps(identity, indent=2) + '\n')
        tables = json_query('USE [ko_reference]; SELECT s.name AS [schema],t.name, SUM(p.rows) AS [rows] FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id JOIN sys.partitions p ON p.object_id=t.object_id AND p.index_id IN (0,1) GROUP BY s.name,t.name ORDER BY s.name,t.name')
        columns = json_query('USE [ko_reference]; SELECT s.name AS [schema],t.name AS [table],c.column_id,c.name,y.name AS [type],c.max_length,c.precision,c.scale,c.is_nullable FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id JOIN sys.columns c ON c.object_id=t.object_id JOIN sys.types y ON y.user_type_id=c.user_type_id ORDER BY s.name,t.name,c.column_id')
        for filename, value in [('tables.json', tables), ('columns.json', columns)]:
            (output / filename).write_text(json.dumps(value, indent=2) + '\n')
        procedures = json_query("USE [ko_reference]; SELECT o.name, m.definition FROM sys.sql_modules m JOIN sys.objects o ON o.object_id=m.object_id WHERE o.name IN ('INSERT_FRIEND_LIST','DELETE_FRIEND_LIST') ORDER BY o.name")
        (output / 'friend-procedures.json').write_text(json.dumps(procedures, indent=2) + '\n')
        names = json_query("USE [ko_reference]; SELECT o.name, o.type_desc AS [type] FROM sys.objects o WHERE o.type IN ('P','FN','IF','TF','V','TR') ORDER BY o.type, o.name")
        (output / 'procedure-names.json').write_text(json.dumps(names, indent=2) + '\n')
        if procedure_names:
            # Names come solely from the fixed allowlist; definitions are text, never executed.
            quoted = ','.join("N'" + name + "'" for name in sorted(set(procedure_names)))
            texts = json_query("USE [ko_reference]; SELECT o.name, m.definition FROM sys.sql_modules m JOIN sys.objects o ON o.object_id=m.object_id WHERE o.name IN (" + quoted + ") ORDER BY o.name")
            (output / 'procedures.json').write_text(json.dumps(texts, ensure_ascii=False, indent=2) + '\n')
        exports = []
        for table in sorted(set(definitions)):
            # Names come solely from the fixed allowlist. JSON is data, never SQL.
            rows = json_query(f'USE [ko_reference]; SELECT * FROM [dbo].[{table}]')
            expected = next(t['rows'] for t in tables if t['schema'] == 'dbo' and t['name'] == table)
            if len(rows) != expected:
                raise RuntimeError('definition export row-count mismatch: ' + table)
            path = output / (table + '.json')
            path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
            with path.open('rb') as stream:
                exports.append({'table': table, 'rows': len(rows), 'sha256': hashlib.file_digest(stream, 'sha256').hexdigest()})
        (output / 'exports.json').write_text(json.dumps(exports, indent=2) + '\n')
        print(f'Restored read-only reference: {len(tables)} tables, {len(columns)} columns; local metadata in {output}', flush=True)
    finally:
        envfile.unlink(missing_ok=True)
        if created:
            run(['docker', 'rm', '-f', name])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backup', type=Path)
    parser.add_argument('--output', type=Path, default=Path('build/ko-completion/database'))
    parser.add_argument("--table", action="append", choices=sorted(DEFINITION_TABLES), default=[], help="also export this definition table to ignored local JSON (repeatable)")
    parser.add_argument("--procedure", action="append", choices=sorted(PROCEDURES), default=[], help="also export this stored procedure's text (never executed) to ignored local JSON (repeatable)")
    args = parser.parse_args()
    inspect(args.backup, args.output, args.table, args.procedure)
