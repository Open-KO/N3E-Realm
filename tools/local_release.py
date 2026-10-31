"""A release of this tree on this machine, for the launcher (docs/manual-testing.md).

  python tools/local_release.py [--port 8770] [--client-build build/client]
                                [--package build/packages/moradon]

Packages the client in --client-build (tools/package_client.py), publishes it with
the content package as a release on http://127.0.0.1:PORT (manifest.json, content
index, content-addressed files; spec 04), and serves it until Ctrl-C. The realm is
the local Compose stack: localhost, N3E_PORT (7777), and DISCORD_CLIENT_ID from the
environment or .env. tests/release_smoke.py publishes through the same functions.
"""
import argparse
import hashlib
import http.server
import json
import os
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = "windows-x86_64" if sys.platform == "win32" else "linux-x86_64"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def dotenv(name):
    """`name` from the environment, else from the repository's .env; "" when unset."""
    if os.environ.get(name):
        return os.environ[name]
    env = ROOT / ".env"
    if env.is_file():
        for line in env.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == name:
                return value.strip().strip('"').strip("'")
    return ""


def serve(root, port=0):
    """An HTTP server for `root` on 127.0.0.1 in a thread; (server, base URL)."""
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(root), **k)

        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def publish(web, url, archive, package, realm, version="local"):
    """Writes manifest.json for client `archive` (a path) and content `package` (a
    built package directory) under `web`, served at `url`; returns the manifest."""
    web, archive, package = Path(web), Path(archive), Path(package)
    client = archive.read_bytes()
    if archive.parent.resolve() != web.resolve():
        (web / archive.name).write_bytes(client)
    (web / "store").mkdir(exist_ok=True)
    files = []
    for path in sorted(p for p in package.rglob("*") if p.is_file()):
        data = path.read_bytes()
        (web / "store" / sha(data)).write_bytes(data)
        files.append({"path": path.relative_to(package).as_posix(), "sha256": sha(data), "size": len(data)})
    content = sha((package / "release.bin").read_bytes())
    index = json.dumps({"schema": 1, "hash": content, "files": files}).encode()
    (web / f"content-{content}.index.json").write_bytes(index)
    manifest = {
        "schema": 1, "release": version, "published_at": "2026-10-31T00:00:00Z", "realm": realm,
        "launcher": {"version": "0.0.0", "min_version": "0.0.0", "artifacts": {}},
        "client": {"version": version, "artifacts": {
            PLATFORM: {"url": f"{url}/{archive.name}", "sha256": sha(client), "size": len(client)}}},
        "content": {"game": package.name, "hash": content, "index_url": f"{url}/content-{content}.index.json",
                    "index_sha256": sha(index), "base_url": f"{url}/store/"},
    }
    (web / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


def main():
    sys.path.insert(0, str(ROOT / "tools"))
    from package_client import package as package_client

    args = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    args.add_argument("--port", type=int, default=8770)
    args.add_argument("--client-build", type=Path, default=ROOT / "build/client")
    args.add_argument("--package", type=Path, default=ROOT / "build/packages/moradon")
    a = args.parse_args()
    if not (a.package / "release.bin").is_file():
        raise SystemExit(f"local_release: {a.package} is missing; run make realm-assets")
    client_id = dotenv("DISCORD_CLIENT_ID")
    if not client_id:
        raise SystemExit("local_release: set DISCORD_CLIENT_ID in .env (README, Discord login)")
    web = ROOT / "build/local-release"
    if web.exists():
        for p in sorted(web.rglob("*"), reverse=True):
            p.rmdir() if p.is_dir() else p.unlink()
    web.mkdir(parents=True, exist_ok=True)
    archive = web / f"n3e-client-{PLATFORM}.tar.zst"
    data = package_client(a.client_build, archive)
    server, url = serve(web, a.port)
    # The client version names its install directory: a new one per archive, so the
    # Launcher installs each rebuild instead of keeping the first.
    realm = {"id": "local", "name": "Local Realm", "host": "localhost", "port": int(dotenv("N3E_PORT") or 7777),
             "discord_client_id": client_id}
    m = publish(web, url, archive, a.package, realm, version=f"local-{sha(data)[:12]}")
    print(f"\nServing release {m['release']} (content {m['content']['hash'][:12]}) at {url}/manifest.json")
    print("In another terminal:")
    print(f"  target/release/realm-launcher --add-realm local {url}/manifest.json")
    print("  target/release/realm-launcher --realm local --ca deploy/local/ca.pem")
    print("Ctrl-C stops serving.", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
