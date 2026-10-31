"""The release smoke (specs/06-cd.md "smoke"): one platform's launcher and client
archive, as a player gets them.

  python tests/release_smoke.py --launcher BIN --client ARCHIVE --package DIR
                                [--gl DIR] [--out DIR]

Publishes a release of ARCHIVE and the content package DIR on a loopback file
server (manifest, content index, content-addressed files), runs
`realm-launcher --manifest URL --no-start` in empty per-user directories, then the
installed client's `--self-test` against the installed content and realm.json,
which must exit 0 within 60 s. Nothing leaves this machine. `--gl DIR` copies a
software OpenGL (Mesa's opengl32.dll and friends) next to the installed Windows
client first, for runners without a GPU. Prints SMOKE_OK.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from local_release import publish, serve  # noqa: E402

WINDOWS = sys.platform == "win32"
CLIENT = "n3e-client.exe" if WINDOWS else "n3e-client"
REALM = {"id": "smoke-realm", "name": "Smoke Realm", "host": "localhost", "port": 7777,
         "discord_client_id": "123456789012345678"}


def main():
    args = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    args.add_argument("--launcher", required=True, type=Path)
    args.add_argument("--client", required=True, type=Path, help="the client .tar.zst")
    args.add_argument("--package", required=True, type=Path, help="a built content package")
    args.add_argument("--gl", type=Path, help="DLLs to put next to the Windows client")
    args.add_argument("--out", type=Path, help="keep the run here (default: a temporary directory)")
    a = args.parse_args()
    out = a.out or Path(tempfile.mkdtemp(prefix="n3e-smoke-"))
    shutil.rmtree(out, ignore_errors=True)
    web, home = out / "web", out / "home"
    web.mkdir(parents=True)
    home.mkdir()
    server, url = serve(web)
    try:
        manifest = publish(web, url, a.client.resolve(), a.package.resolve(), REALM, version="smoke")
        env = {k: v for k, v in os.environ.items()
               if k not in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME")}
        if WINDOWS:
            env.update(LOCALAPPDATA=str(home / "local"), APPDATA=str(home / "roaming"))
            data = home / "local/n3e-realm"
        else:
            env.update(HOME=str(home), XDG_DATA_HOME=str(home / "data"), XDG_CONFIG_HOME=str(home / "config"),
                       XDG_CACHE_HOME=str(home / "cache"), XDG_STATE_HOME=str(home / "state"))
            data = home / "data/n3e-realm"
        launched = subprocess.run([str(a.launcher.resolve()), "--manifest", f"{url}/manifest.json", "--no-start"],
                                  env=env, capture_output=True, text=True, timeout=300)
        print(launched.stdout + launched.stderr, end="")
        if launched.returncode != 0:
            raise SystemExit(f"FAIL launcher --no-start exited {launched.returncode}")
        client_dir = data / "client" / manifest["client"]["version"]
        realm = data / "realms" / manifest["realm"]["id"]
        content = realm / "content" / manifest["content"]["hash"]
        for path in (client_dir / CLIENT, realm / "realm.json", content / "release.bin"):
            if not path.is_file():
                raise SystemExit(f"FAIL the launcher did not install {path}")
        print(f"PASS launcher installed client {manifest['client']['version']} and content "
              f"{manifest['content']['hash'][:12]} ({len(list(content.rglob('*')))} entries)")
        if a.gl:
            for dll in a.gl.iterdir():
                if dll.is_file():
                    shutil.copy(dll, client_dir / dll.name)
        checked = subprocess.run([str(client_dir / CLIENT), str(content), "--self-test", "--realm",
                                  str(realm / "realm.json")], env=env, capture_output=True, text=True, timeout=60)
        print(checked.stdout + checked.stderr, end="")
        if checked.returncode != 0 or "self-test ok" not in checked.stdout:
            raise SystemExit(f"FAIL n3e-client --self-test exited {checked.returncode}")
        print("PASS installed client --self-test")
    finally:
        server.shutdown()
        server.server_close()
    print("SMOKE_OK")


main()
