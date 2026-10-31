"""The launcher (specs/04-launcher.md, roadmap M4).

Publishes test releases on a loopback file server (manifest with ETag, content index,
content-addressed files, client archives) and runs `realm-launcher` against them in
disposable XDG directories. The client in these releases is a stub that records its
argv and exits as told. Covers spec 04 acceptance tests 1-11, plus the schema, network
and archive-path refusals.

The graphical branch (N3E_GRAPHICAL=1) puts the real test client and the demo package
in a release, starts a server, and checks the launcher's client connects to the realm,
and that a realm with other content makes the real client exit 3 and the launcher 20.
"""
import hashlib
import http.server
import io
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import threading
import time
import uuid
from compression import zstd

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
launcher = str(Path(os.environ.get("N3E_TEST_LAUNCHER", "target/debug/realm-launcher")).resolve())
out = ROOT / "build/live/launcher"
shutil.rmtree(out, ignore_errors=True)
out.mkdir(parents=True)
web = out / "web"
web.mkdir()
home = out / "home"
GRAPHICAL = "--graphical" in sys.argv or os.environ.get("N3E_GRAPHICAL") == "1"


def sha(b):
    return hashlib.sha256(b).hexdigest()


class Server:
    """Serves `web/`; the manifest with an ETag; counts requests; can go offline."""

    def __init__(self):
        self.requests = []
        self.lock = threading.Lock()
        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                path = web / self.path.lstrip("/").split("?")[0]
                if not path.is_file() or ".." in self.path:
                    with server.lock:
                        server.requests.append((self.path, 404))
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                data = path.read_bytes()
                tag = '"' + sha(data)[:16] + '"'
                if self.headers.get("If-None-Match") == tag:
                    status, body = 304, b""
                else:
                    status, body = 200, data
                    span = self.headers.get("Range")
                    if span and span.startswith("bytes="):
                        start = int(span[6:].split("-")[0])
                        status, body = 206, data[start:]
                with server.lock:
                    server.requests.append((self.path, status))
                self.send_response(status)
                self.send_header("ETag", tag)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.http = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.http.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def take(self):
        with self.lock:
            taken, self.requests = self.requests, []
        return taken

    def stop(self):
        self.http.shutdown()
        self.http.server_close()


def archive(entries):
    """A .tar.zst of (name, bytes, mode) entries."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        for name, data, mode in entries:
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), mode
            tar.addfile(info, io.BytesIO(data))
    return zstd.compress(raw.getvalue())


STUB = b"""#!/usr/bin/env python3
# A client for the launcher's tests: records argv and realm.json, then exits as told.
import json, os, sys, time
log = os.environ["STUB_LOG"]
count = sum(1 for _ in open(log)) if os.path.exists(log) else 0
realm = json.load(open(sys.argv[sys.argv.index("--realm") + 1]))
with open(log, "a") as f:
    f.write(json.dumps({"argv": sys.argv, "realm": realm, "version": os.environ.get("STUB_VERSION_MARK"),
                        "exe": os.path.abspath(sys.argv[0])}) + "\\n")
if os.environ.get("STUB_PUBLISH") and count == 0:
    src, dst = os.environ["STUB_PUBLISH"].split("|")
    os.replace(src, dst)
time.sleep(float(os.environ.get("STUB_SLEEP", "0")))
codes = os.environ.get("STUB_EXIT", "0").split(",")
sys.exit(int(codes[min(count, len(codes) - 1)]))
"""


def client_release(version, body=STUB, extra=()):
    """Publishes a client archive; returns its artifact entry."""
    data = archive([("n3e-client", body, 0o755), (f"VERSION-{version}", version.encode(), 0o644), *extra])
    name = f"n3e-client-{version}.tar.zst"
    (web / name).write_bytes(data)
    return {"url": f"{srv.url}/{name}", "sha256": sha(data), "size": len(data)}


def content_release(files):
    """Publishes a package's files into the store and its index; returns the manifest's
    content entry. `files` maps path -> bytes and must include release.bin."""
    (web / "store").mkdir(exist_ok=True)
    for data in files.values():
        (web / "store" / sha(data)).write_bytes(data)
    h = sha(files["release.bin"])
    index = json.dumps({"schema": 1, "hash": h, "files": [
        {"path": p, "sha256": sha(d), "size": len(d)} for p, d in sorted(files.items())]}).encode()
    (web / f"content-{h}.index.json").write_bytes(index)
    return {"game": "demo", "hash": h, "index_url": f"{srv.url}/content-{h}.index.json",
            "index_sha256": sha(index), "base_url": f"{srv.url}/store/"}


def manifest(path, release, client, client_version, content, launcher_version="0.0.1", min_version="0.0.1",
             launcher_artifact=None, realm_id="test-realm", port=7777, schema=1):
    m = {"schema": schema, "release": release, "published_at": "2026-10-31T00:00:00Z",
         "realm": {"id": realm_id, "name": "Test Realm", "host": "localhost", "port": port,
                   "discord_client_id": "123456789012345678"},
         "launcher": {"version": launcher_version, "min_version": min_version,
                      "artifacts": {"linux-x86_64": launcher_artifact or
                                    {"url": f"{srv.url}/none", "sha256": "0" * 64, "size": 1}}},
         "client": {"version": client_version, "artifacts": {"linux-x86_64": client}},
         "content": content}
    (web / path).write_text(json.dumps(m))
    return m


def env(**extra):
    e = {"PATH": os.environ["PATH"], "HOME": str(home), "XDG_DATA_HOME": str(home / "data"),
         "XDG_CONFIG_HOME": str(home / "config"), "XDG_CACHE_HOME": str(home / "cache"),
         "STUB_LOG": str(out / "stub.log")}
    e.update(extra)
    return e


def launch(*args, **extra):
    """(exit code, output, seconds) of one launcher run."""
    started = time.monotonic()
    p = subprocess.run([launcher, *args], env=env(**extra), capture_output=True, text=True, timeout=120)
    return p.returncode, p.stdout + p.stderr, time.monotonic() - started


def stub_runs():
    log = out / "stub.log"
    runs = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    log.unlink(missing_ok=True)
    return runs


def fetched(requests, prefix):
    return [p for p, status in requests if p.startswith(prefix) and status in (200, 206)]


data, cfg = home / "data/n3e-realm", home / "config/n3e-realm"
package = {f"file-{i}.bin": f"asset {i}".encode() * (i + 1) for i in range(6)}
package["release.bin"] = b"release one"
package["sub/dir/nested.bin"] = b"nested"
srv = Server()
try:
    # Nothing installed and nothing reachable: exit 10 naming where to download.
    code, text, _ = launch("--manifest", "http://127.0.0.1:9/releases/latest/download/manifest.json")
    assert code == 10 and "Downloads: http://127.0.0.1:9/releases/latest" in text, (code, text)
    code, text, _ = launch("--manifest", "http://example.com/manifest.json")
    assert code == 11 and "plain http is accepted only on this machine" in text, (code, text)
    print("PASS nothing installed: unreachable releases exit 10 with the download address; "
          "plain http off this machine refused")

    # 1. Clean install.
    c1 = client_release("2026.10.31-a")
    k1 = content_release(package)
    manifest("manifest.json", "r1", c1, "2026.10.31-a", k1)
    code, text, _ = launch("--add-realm", "test", f"{srv.url}/manifest.json")
    assert code == 0 and json.loads((cfg / "realms.json").read_text())["realms"]["test"]["manifest"].endswith(
        "/manifest.json"), (code, text)
    srv.take()
    code, text, _ = launch("--realm", "test")
    assert code == 0, (code, text)
    realm = data / "realms/test-realm"
    content_dir = realm / "content" / k1["hash"]
    assert (data / "client/2026.10.31-a/n3e-client").stat().st_mode & 0o111
    for p, d in package.items():
        assert (content_dir / p).read_bytes() == d, p
        assert (data / "store" / sha(d)).is_file()
        assert (content_dir / p).stat().st_ino == (data / "store" / sha(d)).stat().st_ino, "not a hard link"
    for name in ["realm.json", "manifest.json", "state.json"]:
        assert (realm / name).is_file(), name
    assert json.loads((realm / "realm.json").read_text()) == {
        "id": "test-realm", "name": "Test Realm", "host": "localhost", "port": 7777,
        "discord_client_id": "123456789012345678"}
    state = json.loads((realm / "state.json").read_text())
    assert state["installed"] == {"client": "2026.10.31-a", "content": k1["hash"]}, state
    assert json.loads((cfg / "realms.json").read_text())["realms"]["test"]["id"] == "test-realm"
    [run] = stub_runs()
    assert run["argv"][1:] == [str(content_dir), "--realm", str(realm / "realm.json")], run["argv"]
    assert run["exe"] == str(data / "client/2026.10.31-a/n3e-client"), run
    got = srv.take()
    assert len(fetched(got, "/store/")) == len(package), got
    print(f"PASS clean install: client, {len(package)} content files hard-linked from the store, "
          "realm.json/manifest.json/state.json, profile pinned, client argv (test 1)")

    # 2. No-op: a 304 and nothing else; the client starts within a second.
    code, text, took = launch("--realm", "test")
    assert code == 0 and len(stub_runs()) == 1, (code, text)
    got = srv.take()
    assert got == [("/manifest.json", 304)], got
    assert took < 1, took
    print(f"PASS no-op: one 304, no downloads, client started in {took:.2f} s (test 2)")

    # 3. A package differing in two files downloads exactly two; the third version
    # prunes the first and the store entries only it used.
    v2 = dict(package, **{"file-0.bin": b"changed zero", "release.bin": b"release two"})
    k2 = content_release(v2)
    manifest("manifest.json", "r2", c1, "2026.10.31-a", k2)
    code, text, _ = launch("--realm", "test", "--ca", "/tmp/test-ca.pem")
    assert code == 0, (code, text)
    got = srv.take()
    assert sorted(fetched(got, "/store/")) == sorted(f"/store/{sha(d)}" for d in [b"changed zero", b"release two"]), got
    assert (realm / "content" / k1["hash"]).is_dir() and (realm / "content" / k2["hash"]).is_dir()
    [run] = stub_runs()
    assert run["argv"][-2:] == ["--ca", "/tmp/test-ca.pem"], run["argv"]
    v3 = dict(v2, **{"file-1.bin": b"changed one", "release.bin": b"release three"})
    k3 = content_release(v3)
    manifest("manifest.json", "r3", c1, "2026.10.31-a", k3)
    code, text, _ = launch("--realm", "test")
    assert code == 0, (code, text)
    stub_runs()
    assert not (realm / "content" / k1["hash"]).exists(), "oldest package kept"
    assert (realm / "content" / k2["hash"]).is_dir() and (realm / "content" / k3["hash"]).is_dir()
    only_v1 = [sha(package["file-0.bin"]), sha(package["release.bin"])]
    assert all(not (data / "store" / h).exists() for h in only_v1), "store kept v1-only files"
    shared = sha(package["file-2.bin"])
    assert (data / "store" / shared).is_file()
    print("PASS content update: exactly the 2 changed files fetched, the old package kept; a third version "
          "prunes the oldest and its store-only files (test 3)")

    # 4. A corrupt client archive: exit 11, nothing changed, the previous version runs.
    c_bad = client_release("2026.11.01-b")
    c_bad = dict(c_bad, sha256="f" * 64)
    manifest("manifest.json", "r4", c_bad, "2026.11.01-b", k3)
    code, text, _ = launch("--realm", "test")
    assert code == 11 and "verification failed" in text, (code, text)
    assert not (data / "client/2026.11.01-b").exists()
    assert json.loads((realm / "state.json").read_text())["installed"]["client"] == "2026.10.31-a"
    assert stub_runs() == []
    code, text, _ = launch("--realm", "test", "--no-update")
    [run] = stub_runs()
    assert code == 0 and run["exe"].endswith("2026.10.31-a/n3e-client"), (code, text, run)
    print("PASS corrupt artifact: exit 11, nothing changed, --no-update starts the previous version (test 4)")

    # 9. Index paths that would leave the package; a client archive entry that would.
    for bad in ["../x", "/abs"]:
        files = {"release.bin": b"bad paths " + bad.encode(), "ok.bin": b"ok"}
        k = content_release(files)
        index = json.loads((web / f"content-{k['hash']}.index.json").read_text())
        index["files"][0]["path"] = bad
        raw = json.dumps(index).encode()
        (web / f"content-{k['hash']}.index.json").write_bytes(raw)
        k["index_sha256"] = sha(raw)
        manifest("manifest.json", "r9", c1, "2026.10.31-a", k)
        code, text, _ = launch("--realm", "test")
        assert code == 11 and "escapes the package" in text, (bad, code, text)
    evil = client_release("2026.11.02-e", extra=[("../evil", b"x", 0o644)])
    manifest("manifest.json", "r9b", evil, "2026.11.02-e", k3)
    code, text, _ = launch("--realm", "test")
    assert code == 11 and "refusing entry ../evil" in text, (code, text)
    assert not (data / "client/evil").exists() and not (data / "evil").exists()
    stub_runs()
    print("PASS path safety: index entries ../x and /abs and an archive entry ../evil refused, exit 11 (test 9)")

    # Schema: an unknown manifest schema says to update the launcher by hand.
    manifest("manifest.json", "r-schema", c1, "2026.10.31-a", k3, schema=2)
    code, text, _ = launch("--realm", "test")
    assert code == 12 and "Update the launcher manually" in text, (code, text)
    print("PASS unknown manifest schema: exit 12, update the launcher manually")

    # 7. The client says "update required" and the release has not moved: exit 20.
    manifest("manifest.json", "r3", c1, "2026.10.31-a", k3)
    srv.take()
    code, text, _ = launch("--realm", "test", STUB_EXIT="3")
    assert code == 20 and "CD ordering bug" in text, (code, text)
    assert len(stub_runs()) == 1
    assert [p for p, _ in srv.take()] == ["/manifest.json", "/manifest.json"], "manifest not refetched once"
    # ... and when the release has moved, the launcher updates and starts it once more.
    c2 = client_release("2026.11.03-c")
    manifest("next.json", "r5", c2, "2026.11.03-c", k3)
    code, text, _ = launch("--realm", "test", STUB_EXIT="3,0",
                           STUB_PUBLISH=f"{web / 'next.json'}|{web / 'manifest.json'}")
    runs = stub_runs()
    assert code == 0 and [r["exe"].split("/")[-2] for r in runs] == ["2026.10.31-a", "2026.11.03-c"], (code, text, runs)
    print("PASS update required: unchanged release -> exit 20 with the ordering message; "
          "a newer release -> updated and the client restarted once (test 7)")

    # 10. Two launchers at once: one client.
    procs = [subprocess.Popen([launcher, "--realm", "test"], env=env(STUB_SLEEP="2"), stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True) for _ in range(2)]
    texts = [p.communicate(timeout=60)[0] for p in procs]
    assert [p.returncode for p in procs] == [0, 0], texts
    assert sum("already running" in t for t in texts) == 1, texts
    assert len(stub_runs()) == 1
    print("PASS lock: two concurrent launches, one says already running, one client (test 10)")

    # 6. min_version above this launcher with a broken launcher artifact: manual URL, no client.
    broken = {"url": f"{srv.url}/realm-launcher-broken", "sha256": "e" * 64, "size": 10}
    (web / "realm-launcher-broken").write_bytes(b"not an elf")
    manifest("manifest.json", "r6", c2, "2026.11.03-c", k3, launcher_version="0.5.0", min_version="0.5.0",
             launcher_artifact=broken)
    code, text, _ = launch("--realm", "test")
    assert code == 11 and "older than the realm allows" in text and srv.url in text, (code, text)
    assert stub_runs() == []
    print("PASS min_version: a broken self-update leaves exit 11 with the manual download address, "
          "no client (test 6)")

    # 5. Self-update: a newer launcher is installed and re-executed; the client still starts.
    next_dir = ROOT / "build/launcher-next"
    subprocess.run(["cargo", "build", "--locked", "-p", "realm-launcher", "--target-dir", str(next_dir)],
                   env={**os.environ, "REALM_LAUNCHER_VERSION": "9.9.9"}, check=True, capture_output=True)
    new = (next_dir / "debug/realm-launcher").read_bytes()
    (web / "realm-launcher-9.9.9").write_bytes(new)
    artifact = {"url": f"{srv.url}/realm-launcher-9.9.9", "sha256": sha(new), "size": len(new)}
    manifest("manifest.json", "r7", c2, "2026.11.03-c", k3, launcher_version="9.9.9", min_version="0.5.0",
             launcher_artifact=artifact)
    code, text, _ = launch("--realm", "test")
    assert code == 0 and "Updating the launcher to 9.9.9" in text, (code, text)
    assert os.readlink(data / "launcher/current") == "9.9.9/realm-launcher"
    v = subprocess.run([str(data / "launcher/current"), "--version"], capture_output=True, text=True).stdout
    assert v.startswith("realm-launcher 9.9.9 "), v
    assert len(stub_runs()) == 1
    # The old binary, run again by hand, hands over to the installed newer one.
    code, text, _ = launch("--realm", "test")
    assert code == 0 and "Updating the launcher" not in text and len(stub_runs()) == 1, (code, text)
    print("PASS self-update: downloaded, checked with --version, current swapped, re-executed; the client "
          "starts; an old copy hands over to it (test 5)")

    # 11. A second realm profile; a manifest that changes its realm id is refused.
    (web / "second").mkdir()
    k_second = content_release({"release.bin": b"second realm", "a.bin": b"a"})
    manifest("second/manifest.json", "s1", c2, "2026.11.03-c", k_second, launcher_version="9.9.9",
             launcher_artifact=artifact, realm_id="second-realm", port=7800)
    code, text, _ = launch("--add-realm", "second", f"{srv.url}/second/manifest.json")
    assert code == 0, (code, text)
    code, text, _ = launch("--realm", "second")
    [run] = stub_runs()
    assert code == 0 and run["realm"]["id"] == "second-realm" and run["realm"]["port"] == 7800, (code, text, run)
    assert run["argv"][run["argv"].index("--realm") + 1] == str(data / "realms/second-realm/realm.json")
    manifest("second/manifest.json", "s2", c2, "2026.11.03-c", k_second, launcher_version="9.9.9",
             launcher_artifact=artifact, realm_id="hijacked")
    code, text, _ = launch("--realm", "second")
    assert code == 11 and "pinned to `second-realm`" in text and stub_runs() == [], (code, text)
    print("PASS profiles: --add-realm and --realm start the second realm's realm.json; a manifest changing "
          "realm.id is refused (test 11)")

    # 8. Offline: the installed client starts with a warning; --check says why it cannot tell.
    code, text, _ = launch("--realm", "test", "--check")
    assert code == 0 and "client: 2026.11.03-c, installed" in text, (code, text)
    srv.stop()
    code, text, _ = launch("--realm", "test")
    assert code == 0 and "starting what is installed" in text and len(stub_runs()) == 1, (code, text)
    code, text, _ = launch("--realm", "test", "--check")
    assert code == 10 and "cannot reach" in text, (code, text)
    print("PASS offline: the installed client starts with a warning; --check exits 10 with a network message (test 8)")
    srv = Server()

    if GRAPHICAL:
        sys.path.insert(0, str(ROOT / "tests"))
        from readiness import free_ports, wait_postgres
        from isolation import DISPOSABLE_POSTGRES
        server_binary = str(Path(os.environ.get("N3E_TEST_SERVER", "target/debug/n3e-server")).resolve())
        name = "n3e-launcher-" + uuid.uuid4().hex[:10]
        containers, server = [], None
        try:
            for suffix, image, cp, extra in [
                ("", "postgres:17.4-bookworm@sha256:304ab813518754228f9f792f79d6da36359b82d8ecf418096c636725f8c930ad",
                 5432, ["-e", "POSTGRES_USER=n3e", "-e", "POSTGRES_PASSWORD=test-only", "-e", "POSTGRES_DB=n3e",
                        *DISPOSABLE_POSTGRES]),
                ("-redis", "redis:7.4.2-bookworm@sha256:fbdbaea47b9ae4ecc2082ecdb4e1cea81e32176ffb1dcf643d422ad07427e5d9",
                 6379, []),
            ]:
                subprocess.run(["docker", "run", "--rm", "-d", "--name", name + suffix, *extra, "-p",
                                f"127.0.0.1::{cp}", image], check=True, capture_output=True)
                containers.append(name + suffix)
            pg = wait_postgres(name)
            redis = subprocess.run(["docker", "port", name + "-redis", "6379"], capture_output=True,
                                   text=True).stdout.split()[0]
            listen, health, admin = free_ports(3)
            # Discord login against an API nobody answers: the client gets as far as
            # printing the authorize address, which is all this checks.
            senv = {k: v for k, v in os.environ.items() if k not in ("N3E_LEGACY_LOGIN", "DISCORD_CLIENT_ID",
                                                                     "DISCORD_CLIENT_SECRET")}
            senv.update(DATABASE_URL=f"host=127.0.0.1 port={pg} user=n3e password=test-only dbname=n3e",
                        REDIS_ADDRESS=redis, N3E_PACKAGE=str(ROOT / "build/packages/demo"), N3E_REALM=f"test-{name}",
                        N3E_LISTEN=f"127.0.0.1:{listen}", N3E_HEALTH=f"127.0.0.1:{health}",
                        N3E_ADMIN_LISTEN=f"127.0.0.1:{admin}", DISCORD_CLIENT_ID="123456789012345678",
                        DISCORD_CLIENT_SECRET="test-only", N3E_DISCORD_API="http://127.0.0.1:9/api")
            subprocess.run([server_binary, "migrate"], env=senv, check=True, capture_output=True)
            subprocess.run([server_binary, "convert-progression"], env={**senv, "N3E_TEST_PROGRESSION": "disposable"},
                           check=True, capture_output=True)
            server = subprocess.Popen([server_binary], env=senv, stdout=open(out / "server.log", "w"),
                                      stderr=subprocess.STDOUT)
            # The real client in a release: the harness build, told to start the Discord step itself.
            real = str(ROOT / "build/client/n3e-test-client")
            wrapper = (f'#!/bin/sh\necho $$ > "{out}/client.pid"\n'
                       f'exec "{real}" "$@" --auto-login\n').encode()
            creal = client_release("2026.11.04-real", body=wrapper)
            demo = {str(p.relative_to(ROOT / "build/packages/demo")): p.read_bytes()
                    for p in (ROOT / "build/packages/demo").rglob("*") if p.is_file()}
            kdemo = content_release(demo)
            (web / "real").mkdir(exist_ok=True)
            manifest("real/manifest.json", "g1", creal, "2026.11.04-real", kdemo, launcher_version="9.9.9",
                     launcher_artifact=artifact, realm_id="real-realm", port=listen)
            assert launch("--add-realm", "real", f"{srv.url}/real/manifest.json")[0] == 0
            deadline = time.monotonic() + 60
            while True:
                assert server.poll() is None, (out / "server.log").read_text()[-3000:]
                try:
                    socket.create_connection(("127.0.0.1", listen), 1).close()
                    break
                except OSError:
                    assert time.monotonic() < deadline, "server not listening"
                    time.sleep(0.2)
            proc = subprocess.Popen([launcher, "--realm", "real", "--ca", str(ROOT / "deploy/local/ca.pem")],
                                    env={**os.environ, **env(N3E_TEST_NO_BROWSER="1")}, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True)
            lines = []
            for line in proc.stdout:
                lines.append(line)
                if line.startswith("Open this address to log in with Discord: "):
                    os.kill(int((out / "client.pid").read_text()), signal.SIGTERM)
            proc.wait(60)
            (out / "client-real.log").write_text("".join(lines))
            assert any(l.startswith("Open this address") for l in lines), "".join(lines)[-3000:]
            print("PASS graphical: the launcher installs the real client and the demo package from a release; "
                  "the client connects to the realm and starts the Discord login")
            # Another package: the realm refuses it, the client exits 3, the release has not moved: 20.
            alt = ROOT / "build/packages/demo-alt"
            kother = content_release({str(p.relative_to(alt)): p.read_bytes() for p in alt.rglob("*") if p.is_file()})
            assert kother["hash"] != kdemo["hash"]
            manifest("real/manifest.json", "g2", creal, "2026.11.04-real", kother, launcher_version="9.9.9",
                     launcher_artifact=artifact, realm_id="real-realm", port=listen)
            p = subprocess.run([launcher, "--realm", "real", "--ca", str(ROOT / "deploy/local/ca.pem")],
                               env={**os.environ, **env(N3E_TEST_NO_BROWSER="1")}, capture_output=True, text=True,
                               timeout=120)
            (out / "client-mismatch.log").write_text(p.stdout + p.stderr)
            assert p.returncode == 20 and "does not match the realm" in p.stderr, (p.returncode, p.stderr[-3000:])
            print("PASS graphical update required: the realm refuses other content, the real client exits 3, "
                  "the launcher exits 20")
        finally:
            if server is not None:
                server.terminate()
                server.wait(10)
            for c in containers:
                subprocess.run(["docker", "rm", "-f", c], capture_output=True)
    print("LAUNCHER_OK")
finally:
    try:
        srv.stop()
    except Exception:
        pass
