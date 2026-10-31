#!/usr/bin/env python3
"""Provision a private local test account and enter the already-running field."""
import json
import os
import pathlib
import secrets
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "tests"))
from world_peer import Peer

credentials = ROOT / "build/ko-field-login.json"
if credentials.exists():
    account = json.loads(credentials.read_text())
else:
    account = dict(account="field" + secrets.token_hex(4), password=secrets.token_urlsafe(24))
    subprocess.run(["docker", "compose", "-p", "n3e-ko-field", "exec", "-T", "server",
                    "n3e-server", "account-create", account["account"]],
                   input=account["password"] + "\n", text=True, check=True)
    with os.fdopen(os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
        json.dump(account, f)
p = Peer(7778, account["account"], account["password"],
         content=(ROOT / "build/packages/ko-field/release.sha256").read_text().strip(), game="kotest")
if not p.characters:
    p.create("Explorer")
p.s.close()
if "--provision-only" in sys.argv:
    print("Local test account and Explorer ready; credentials stay in ignored build/.")
else:
    env = os.environ.copy()
    env.update(N3E_TEST_ACCOUNT=account["account"], N3E_TEST_PASSWORD=account["password"])
    args = [str(ROOT / "build/client/n3e-test-client"), "build/packages/ko-field",
            "--connect", "localhost:7778", "--ca", "deploy/local/ca.pem", "--auto-login"]
    args += sys.argv[1:]
    os.execve(args[0], args, env)
