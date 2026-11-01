"""A zip for playing the local realm from a Windows PC on the LAN (docs/manual-testing.md).

  python tools/windows_kit.py --host 192.168.1.20 [--run RUN_ID]
                              [--package build/packages/moradon] [--out build/windows-kit.zip]

Takes the Windows client and launcher CI built (the `client-windows-x86_64` artifact
of RUN_ID, else of the newest successful `ci` run on master; needs `gh`), and adds
the content package the local stack serves, a realm.json naming this machine at
--host (an address the server certificate names: N3E_LOCAL_NAMES, deploy/local-ca.sh),
the local CA's ca.pem, and three .bat files: self-test, play, and forget-login.
DISCORD_CLIENT_ID comes from the environment or .env. Nothing here is secret.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from local_release import dotenv  # noqa: E402

ARTIFACT = "client-windows-x86_64"
README = """N3E local realm test kit, for Windows (docs/manual-testing.md in the repository).

1. self-test.bat   checks the client, the package, the certificates and OpenGL. It
                   must end with "self-test ok".
2. play.bat        starts the game against {host}:{port}. ENTER opens Discord in your
                   browser; after you authorize, the game logs you in. Starting it
                   again logs in without the browser (the token is kept 30 days in
                   %APPDATA%\\n3e-realm\\local\\session.json). The window is
                   1280x1024; for another of KO's sizes run it from a command
                   prompt as  play.bat --fixed-window 1024x768  (or 1600x1200),
                   and add --fullscreen for full screen at that size.
3. forget-login.bat deletes that token, so the next start asks Discord again.

Windows may warn that the program is from an unknown publisher (it is unsigned):
More info, then Run anyway. The game's console window shows its messages; copy
them into your report if something goes wrong.
"""


def latest_run():
    out = subprocess.run(["gh", "run", "list", "--workflow", "ci", "--branch", "master", "--status", "success",
                          "--limit", "10", "--json", "databaseId,headSha"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout
    for run in json.loads(out):
        names = subprocess.run(["gh", "api", f"repos/{{owner}}/{{repo}}/actions/runs/{run['databaseId']}/artifacts",
                                "--jq", ".artifacts[].name"], cwd=ROOT, capture_output=True, text=True,
                               check=True).stdout.split()
        if ARTIFACT in names:
            return str(run["databaseId"]), run["headSha"]
    raise SystemExit(f"windows_kit: no successful ci run on master has {ARTIFACT}; pass --run")


def main():
    args = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    args.add_argument("--host", required=True, help="this machine's LAN address, as the Windows PC reaches it")
    args.add_argument("--run", help="the ci run whose Windows artifact to use")
    args.add_argument("--package", type=Path, default=ROOT / "build/packages/moradon")
    args.add_argument("--out", type=Path, default=ROOT / "build/windows-kit.zip")
    a = args.parse_args()
    if not (a.package / "release.bin").is_file():
        raise SystemExit(f"windows_kit: {a.package} is missing; run make realm-assets")
    if not re.fullmatch(r"[A-Za-z0-9.-]+", a.host):
        raise SystemExit(f"windows_kit: bad --host {a.host}")
    client_id = dotenv("DISCORD_CLIENT_ID")
    if not client_id:
        raise SystemExit("windows_kit: set DISCORD_CLIENT_ID in .env (README, Discord login)")
    ca = ROOT / "deploy/local/ca.pem"
    check = subprocess.run(["openssl", "verify", "-purpose", "sslserver",
                            "-verify_ip" if re.fullmatch(r"[0-9.]+", a.host) else "-verify_hostname", a.host,
                            "-CAfile", str(ca), str(ROOT / "deploy/local/server.pem")], capture_output=True, text=True)
    if check.returncode != 0:
        raise SystemExit(f"windows_kit: the local server certificate does not name {a.host}; run\n"
                         f"  N3E_LOCAL_NAMES={a.host} bash deploy/local-ca.sh\nand restart the server")
    run, sha = (a.run, "") if a.run else latest_run()
    port = int(dotenv("N3E_PORT") or 7777)
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["gh", "run", "download", run, "-n", ARTIFACT, "-D", tmp], cwd=ROOT, check=True)
        archive = Path(tmp) / f"n3e-client-{ARTIFACT.removeprefix('client-')}.tar.zst"
        with tarfile.open(archive, "r:zst") as tar:
            client = tar.extractfile("n3e-client.exe").read()
        launcher = Path(tmp) / "realm-launcher.exe"
        realm = {"id": "local", "name": "Local Realm", "host": a.host, "port": port,
                 "discord_client_id": client_id}
        bat = "@echo off\r\ncd /d \"%~dp0\"\r\n{}\r\npause\r\n"
        a.out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("n3e-kit/n3e-client.exe", client)
            if launcher.is_file():
                z.write(launcher, "n3e-kit/realm-launcher.exe")
            for path in sorted(p for p in a.package.rglob("*") if p.is_file()):
                z.write(path, f"n3e-kit/package/{path.relative_to(a.package).as_posix()}")
            z.writestr("n3e-kit/realm.json", json.dumps(realm, indent=1))
            z.write(ca, "n3e-kit/ca.pem")
            z.writestr("n3e-kit/self-test.bat",
                       bat.format("n3e-client.exe package --self-test --realm realm.json"))
            z.writestr("n3e-kit/play.bat", bat.format("n3e-client.exe package --realm realm.json --ca ca.pem %*"))
            z.writestr("n3e-kit/forget-login.bat",
                       bat.format('del "%APPDATA%\\n3e-realm\\local\\session.json" && echo Forgotten.'))
            z.writestr("n3e-kit/README.txt", README.format(host=a.host, port=port).replace("\n", "\r\n"))
    print(f"{a.out}: ci run {run}{' (' + sha[:7] + ')' if sha else ''}, realm {a.host}:{port}, "
          f"package {a.package.name}")


main()
