#!/usr/bin/env python3
"""Reopen the isolated movement laboratory with private local credentials."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "tests"))
from world_peer import Peer

parser = argparse.ArgumentParser()
parser.add_argument("--ko", action="store_true")
parser.add_argument("--camera", action="store_true")
parser.add_argument("--melee", action="store_true")
parser.add_argument("--damage", action="store_true")
parser.add_argument("--animation", action="store_true")
parser.add_argument("--life", action="store_true")
parser.add_argument("--npc", action="store_true")
parser.add_argument(
    "--second", action="store_true", help="second account in another client"
)
args = parser.parse_args()
mode = next((name for name in ("animation", "life", "npc", "damage", "melee", "camera") if getattr(args, name)), "movement")
name = mode + ("-ko" if args.ko else "")
port = {"movement": 7779, "camera": 7781, "melee": 7783, "damage": 7785, "npc": 7787, "life": 7789, "animation": 7791}[mode] + int(args.ko)
package = ROOT / "build/packages" / name
project = "n3e-" + name
phase = {"movement": "01", "camera": "02", "melee": "03", "damage": "04", "npc": "05", "life": "06", "animation": "07"}[mode]
credentials = ROOT / f"build/ko-{phase}" / f"{name}-login-{2 if args.second else 1}.json"
credentials.parent.mkdir(parents=True, exist_ok=True)
if credentials.exists():
    account = json.loads(credentials.read_text())
else:
    account = dict(
        account="move" + secrets.token_hex(4), password=secrets.token_urlsafe(24)
    )
    subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            project,
            "exec",
            "-T",
            "server",
            "n3e-server",
            "account-create",
            account["account"],
        ],
        input=account["password"] + "\n",
        text=True,
        check=True,
    )
    with os.fdopen(
        os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
    ) as f:
        json.dump(account, f)
manifest = json.loads((package / "recipe.json").read_text())["manifest"]
p = Peer(
    port,
    account["account"],
    account["password"],
    content=(package / "release.sha256").read_text().strip(),
    game=manifest["game_id"],
    protocol=manifest["protocol_version"],
)
if not p.characters:
    p.create("WalkerTwo" if args.second else "Walker")
p.s.close()
env = {
    **os.environ,
    "N3E_TEST_ACCOUNT": account["account"],
    "N3E_TEST_PASSWORD": account["password"],
}
binary = ROOT / "build/client/n3e-test-client"
os.execve(
    binary,
    [
        str(binary),
        str(package),
        "--connect",
        f"localhost:{port}",
        "--ca",
        "deploy/local/ca.pem",
        "--auto-login",
    ],
    env,
)
