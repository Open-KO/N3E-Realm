"""PQ-295: deploy/local-ca.sh renews an expired or nearly expired local pair.

The script makes the git-ignored local development CA and localhost server
certificate that make live's prepare (tests/live.py PREPARE) and the launchers
use. Every case runs in a scratch directory with certificates made here with
chosen validity windows; the real deploy/local pair is never touched.

  python tests/local_ca.py [--script PATH]

A real TLS handshake over a socket pair (Python's ssl, OpenSSL underneath, with
peer verification and the localhost host name, as client/network/handshake.cpp
sets them) checks that what the script leaves is what a client accepts.
"""
import argparse
import datetime
import hashlib
import os
import shutil
import socket
import ssl
import stat
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ("ca.key", "ca.pem", "server.key", "server.pem")
DAY = 86400
EXTENSIONS = """subjectAltName=DNS:localhost
extendedKeyUsage=serverAuth
keyUsage=critical,digitalSignature,keyEncipherment
basicConstraints=critical,CA:FALSE
"""


def stamp(offset):
    t = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=offset)
    return t.strftime("%Y%m%d%H%M%SZ")


def openssl(*args, cwd):
    subprocess.run(["openssl", *args], cwd=cwd, check=True, capture_output=True)


def make_pair(d, ca_life=(-DAY, 20 * DAY), server_life=(-DAY, 20 * DAY), host="localhost"):
    """A pair shaped like the script's, with validity windows (seconds from now)."""
    d.mkdir(parents=True, exist_ok=True)
    openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "ca.key", "-out", "ca.pem",
            "-not_before", stamp(ca_life[0]), "-not_after", stamp(ca_life[1]), "-subj", "/CN=n3e local development CA",
            "-addext", "basicConstraints=critical,CA:TRUE", "-addext", "keyUsage=critical,keyCertSign,cRLSign", cwd=d)
    openssl("req", "-newkey", "rsa:2048", "-nodes", "-keyout", "server.key", "-out", "server.csr",
            "-subj", f"/CN={host}", cwd=d)
    (d / "extensions").write_text(EXTENSIONS.replace("DNS:localhost", f"DNS:{host}"))
    openssl("x509", "-req", "-in", "server.csr", "-CA", "ca.pem", "-CAkey", "ca.key", "-CAcreateserial",
            "-out", "server.pem", "-not_before", stamp(server_life[0]), "-not_after", stamp(server_life[1]),
            "-extfile", "extensions", cwd=d)
    for f in ("ca.key", "server.key"):
        os.chmod(d / f, 0o600)


def snapshot(d):
    out = {}
    for f in FILES:
        p = d / f
        if p.exists():
            s = p.stat()
            out[f] = (hashlib.sha256(p.read_bytes()).hexdigest(), s.st_ino, s.st_mtime_ns)
    return out


def run(script, d, env=None):
    return subprocess.run(["bash", str(script), str(d)], capture_output=True, text=True, timeout=120,
                          env=env or os.environ)


def not_after(pem):
    r = subprocess.run(["openssl", "x509", "-noout", "-enddate", "-in", str(pem)], capture_output=True, text=True,
                       check=True)
    value = r.stdout.strip().split("=", 1)[1]
    return datetime.datetime.strptime(value, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=datetime.timezone.utc)


def handshake(d, ca=None):
    """True when a verifying localhost client accepts d's server pair."""
    server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ctx.load_cert_chain(d / "server.pem", d / "server.key")
    client_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client_ctx.load_verify_locations(ca or d / "ca.pem")
    a, b = socket.socketpair()
    a.settimeout(10)
    b.settimeout(10)
    errors = []

    def serve():
        try:
            with server_ctx.wrap_socket(a, server_side=True) as s:
                s.sendall(b"ok")
        except (ssl.SSLError, OSError) as e:
            errors.append(e)

    t = threading.Thread(target=serve)
    t.start()
    try:
        with client_ctx.wrap_socket(b, server_hostname="localhost") as c:
            got = c.recv(2)
        return got == b"ok"
    except ssl.SSLCertVerificationError:
        return False
    finally:
        b.close()
        t.join(10)
        a.close()


def leaked(output, d):
    """Whether output carries private key material from d."""
    if "PRIVATE KEY" in output:
        return True
    for f in ("ca.key", "server.key"):
        p = d / f
        if p.exists():
            body = [line for line in p.read_text().splitlines() if line and not line.startswith("-----")]
            if any(line in output for line in body):
                return True
    return False


def check_fresh(d, before, result, label):
    """The script renewed: a new valid pair a client accepts, keys private."""
    out = result.stdout + result.stderr
    assert result.returncode == 0, f"{label}: exit {result.returncode}: {out}"
    assert "local-ca: renewing" in result.stderr, f"{label}: no renewal reported: {out}"
    assert not leaked(out, d), f"{label}: key material in output"
    after = snapshot(d)
    for f in FILES:
        assert f in after, f"{label}: {f} missing"
        if f in before:
            assert after[f][0] != before[f][0], f"{label}: {f} not replaced"
    soon = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=29)
    for f in ("ca.pem", "server.pem"):
        assert not_after(d / f) > soon, f"{label}: {f} valid for under 29 days"
    for f, mode in (("ca.key", 0o600), ("server.key", 0o600), ("ca.pem", 0o644), ("server.pem", 0o644)):
        got = stat.S_IMODE((d / f).stat().st_mode)
        assert got == mode, f"{label}: {f} mode {oct(got)}, want {oct(mode)}"
    assert handshake(d), f"{label}: renewed pair refused by a verifying client"
    left = [p.name for p in d.iterdir() if p.name.startswith(".renew.") or p.name in ("server.csr", "extensions", "ca.srl")]
    assert not left, f"{label}: left behind {left}"
    assert "server.pem: OK" in result.stdout, f"{label}: no verify line: {out}"


def check_kept(d, before, result, label):
    """The script left a valid pair exactly as it was."""
    out = result.stdout + result.stderr
    assert result.returncode == 0, f"{label}: exit {result.returncode}: {out}"
    assert "renewing" not in out, f"{label}: renewed a valid pair: {out}"
    assert snapshot(d) == before, f"{label}: valid pair changed"
    assert "server.pem: OK" in result.stdout, f"{label}: no verify line: {out}"
    assert not leaked(out, d), f"{label}: key material in output"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", default=str(ROOT / "deploy/local-ca.sh"))
    script = Path(parser.parse_args().script).resolve()
    (ROOT / "build").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / "build", prefix="local-ca-") as scratch:
        scratch = Path(scratch)
        passed = []

        def case(name):
            d = scratch / name
            return d

        # Fresh directory: a pair is made.
        d = case("fresh")
        check_fresh(d, {}, run(script, d), "fresh")
        # Run again on it: valid, untouched.
        check_kept(d, snapshot(d), run(script, d), "fresh rerun")
        passed.append("fresh")

        # Valid with 8 days left (the margin is 7): untouched.
        d = case("valid")
        make_pair(d, ca_life=(-22 * DAY, 8 * DAY), server_life=(-22 * DAY, 8 * DAY))
        assert handshake(d), "valid fixture refused"
        check_kept(d, snapshot(d), run(script, d), "valid 8 days")
        passed.append("valid")

        # Both expired, as on 2026-10-19 (PQ-292): renewed. The old pair fails a
        # verifying client, which is the prepare failure this fixes.
        d = case("expired")
        make_pair(d, ca_life=(-31 * DAY, -3600), server_life=(-31 * DAY, -3600))
        assert not handshake(d), "expired fixture accepted"
        old_ca = scratch / "expired-old-ca.pem"
        shutil.copy(d / "ca.pem", old_ca)
        before = snapshot(d)
        check_fresh(d, before, run(script, d), "expired")
        assert not handshake(d, ca=old_ca), "renewed server certificate accepted against the old CA"
        passed.append("expired")

        # Near expiry: valid now, under 7 days left.
        d = case("near")
        make_pair(d, ca_life=(-28 * DAY, 2 * DAY), server_life=(-28 * DAY, 2 * DAY))
        assert handshake(d), "near-expiry fixture refused"
        check_fresh(d, snapshot(d), run(script, d), "near expiry")
        passed.append("near")

        # Just inside the margin (7 days less an hour): renewed.
        d = case("edge")
        make_pair(d, ca_life=(-DAY, 7 * DAY - 3600), server_life=(-DAY, 7 * DAY - 3600))
        check_fresh(d, snapshot(d), run(script, d), "7 days less an hour")
        passed.append("edge")

        # Only the CA near expiry; only the server certificate expired.
        d = case("ca-near")
        make_pair(d, ca_life=(-DAY, 3 * DAY), server_life=(-DAY, 20 * DAY))
        check_fresh(d, snapshot(d), run(script, d), "CA near expiry")
        d = case("server-expired")
        make_pair(d, ca_life=(-DAY, 20 * DAY), server_life=(-2 * DAY, -60))
        check_fresh(d, snapshot(d), run(script, d), "server expired")
        passed.append("one-sided")

        # Not yet valid server certificate (clock stepped back): renewed.
        d = case("future")
        make_pair(d, server_life=(DAY, 20 * DAY))
        assert not handshake(d), "not-yet-valid fixture accepted"
        check_fresh(d, snapshot(d), run(script, d), "not yet valid")
        passed.append("future")

        # Broken pairs the old script only failed on: a server key from another
        # pair, a server certificate from another CA, a missing ca.pem, a
        # truncated server.pem, a certificate for another host name.
        d, other = case("mismatch"), case("other")
        make_pair(d)
        make_pair(other)
        shutil.copy(other / "server.key", d / "server.key")
        check_fresh(d, snapshot(d), run(script, d), "key mismatch")
        d = case("foreign")
        make_pair(d)
        shutil.copy(other / "ca.pem", d / "ca.pem")
        check_fresh(d, snapshot(d), run(script, d), "foreign CA")
        d = case("no-ca")
        make_pair(d)
        (d / "ca.pem").unlink()
        check_fresh(d, snapshot(d), run(script, d), "missing ca.pem")
        d = case("truncated")
        make_pair(d)
        (d / "server.pem").write_text((d / "server.pem").read_text()[:200])
        check_fresh(d, snapshot(d), run(script, d), "truncated server.pem")
        d = case("host")
        make_pair(d, host="example.invalid")
        check_fresh(d, snapshot(d), run(script, d), "other host name")
        passed.append("broken")

        # Recovery: an openssl failure part way through a renewal leaves the old
        # files exactly as they were and no scratch directory behind.
        d = case("failing")
        make_pair(d, ca_life=(-31 * DAY, -3600), server_life=(-31 * DAY, -3600))
        before = snapshot(d)
        fake = scratch / "fakebin"
        fake.mkdir()
        real = shutil.which("openssl")
        (fake / "openssl").write_text(
            "#!/bin/sh\nfor a; do [ \"$a\" = -CAcreateserial ] && exit 1; done\nexec " + real + " \"$@\"\n")
        os.chmod(fake / "openssl", 0o755)
        result = run(script, d, env={**os.environ, "PATH": f"{fake}:{os.environ['PATH']}"})
        assert result.returncode != 0, "failed renewal reported success"
        assert snapshot(d) == before, "failed renewal changed the old files"
        assert not [p for p in d.iterdir() if p.name.startswith(".renew.")], "failed renewal left a scratch directory"
        # The next run, with openssl working, renews.
        check_fresh(d, before, run(script, d), "after a failed renewal")
        passed.append("recovery")

        # Two runs at once on an expired pair (two prepares): one renews, the
        # other waits on the lock and finds the new pair valid.
        d = case("race")
        make_pair(d, ca_life=(-31 * DAY, -3600), server_life=(-31 * DAY, -3600))
        before = snapshot(d)
        procs = [subprocess.Popen(["bash", str(script), str(d)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True) for _ in range(3)]
        outs = [p.communicate(timeout=120) for p in procs]
        assert all(p.returncode == 0 for p in procs), f"race: {outs}"
        renewals = sum("local-ca: renewing" in err for _, err in outs)
        assert renewals == 1, f"race: {renewals} renewals"
        assert all(f in snapshot(d) and snapshot(d)[f][0] != before[f][0] for f in FILES), "race: not renewed"
        assert handshake(d), "race: final pair refused"
        passed.append("race")

    print(f"local CA ok ({', '.join(passed)})")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"FAIL local CA: {e}", file=sys.stderr)
        sys.exit(1)
