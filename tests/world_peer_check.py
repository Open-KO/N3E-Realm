"""Checks for the test peer's keepalive (tests/world_peer.py; PQ-112, PQ-120), without
Docker.

A local TLS server stands in for the game server. It answers the handshake and the
login, records when every frame arrives, and can stall a frame it sends half-way:
inside one TLS record, or between the length record and the body record as the
server's writer sends them (`send` in server/src/network.rs). The checks:

- an idle logged-in peer is pinged within the server's 2 s read deadline;
- a receive waiting on a stalled frame does not stop this peer's pings, and a
  frame not whole within the receive's 4 s is kept for the next receive;
- an error inside the keepalive loop, an unexpected ping error, a thread that dies
  and a thread starved past the deadline each make the next peer use raise
  KeepaliveError and keep the process from exiting 0, while the thread keeps
  pinging (or is restarted);
- a peer the server closes, or the test closes, stops being pinged without a
  failure; a peer the test is using, or one whose login reply took 1.8 s or
  2.6 s, is not counted as late; a peer that never logged in is never pinged;
- a loop of pump(.05) and moves, as the suites' route loops run, pings at the
  keepalive cadence rather than once per pump call, and a peer the server closes
  after an Error and LoggedOut it was not waiting for meets an EOF that names
  them (PQ-427).
"""
import contextlib
import io
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import threading
import time
import weakref
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import world_peer  # noqa: E402
from world_peer import DISCONNECTED, KeepaliveError, Peer, blob, fields, integer  # noqa: E402

HERE = Path(__file__).resolve()
# The longest gap between two frames from an idle tended peer: KEEPALIVE plus one
# WAKE, with slack for scheduling. Well under the server's 2 s deadline.
IDLE_GAP = world_peer.KEEPALIVE + world_peer.WAKE + 0.3


def frame(tag, body=b""):
    envelope = blob(tag, body)
    return struct.pack(">I", len(envelope)) + envelope


class Connection:
    """One client connection to the stand-in server, TLS through memory BIOs so a
    send can stop anywhere in the encrypted stream."""

    def __init__(self, sock, context, login_delay=0.0):
        self.sock = sock
        self.login_delay = login_delay  # the server handles Login inline (scrypt, DB)
        self.tls_lock = threading.Lock()  # the SSLObject, used by both threads
        self.wire_lock = threading.Lock()  # socket sends; held across a stall
        self.incoming, self.outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
        self.tls = context.wrap_bio(self.incoming, self.outgoing, server_side=True)
        self.arrivals = []  # (monotonic time, tag) of every frame received
        self.closed = threading.Event()
        threading.Thread(target=self.serve, daemon=True).start()

    def flush(self):
        with self.tls_lock:
            data = self.outgoing.read()
        if data:
            with self.wire_lock:
                self.sock.sendall(data)

    def serve(self):
        try:
            while True:
                with self.tls_lock:
                    try:
                        self.tls.do_handshake()
                        done = True
                    except ssl.SSLWantReadError:
                        done = False
                self.flush()
                if done:
                    break
                chunk = self.sock.recv(65536)
                if not chunk:
                    return
                with self.tls_lock:
                    self.incoming.write(chunk)
            buffer = b""
            while True:
                chunk = self.sock.recv(65536)
                if not chunk:
                    return
                plain = b""
                with self.tls_lock:
                    self.incoming.write(chunk)
                    while True:
                        try:
                            plain += self.tls.read(65536)
                        except (ssl.SSLWantReadError, ssl.SSLZeroReturnError):
                            break
                self.flush()
                buffer += plain
                while len(buffer) >= 4 and len(buffer) >= 4 + struct.unpack(">I", buffer[:4])[0]:
                    n = struct.unpack(">I", buffer[:4])[0]
                    tag = next(iter(fields(buffer[4 : 4 + n])))
                    buffer = buffer[4 + n :]
                    self.arrivals.append((time.monotonic(), tag))
                    if tag == 1:
                        self.send(frame(3))  # handshake accepted
                    elif tag == 5:
                        time.sleep(self.login_delay)  # reading nothing meanwhile
                        self.send(frame(6))  # logged in, no characters
        except OSError:
            return
        finally:
            self.closed.set()

    def encrypt(self, plain):
        with self.tls_lock:
            self.tls.write(plain)
            return self.outgoing.read()

    def send(self, data):
        wire = self.encrypt(data)
        with self.wire_lock:
            self.sock.sendall(wire)

    def stall_in_record(self, data, seconds):
        """Send `data` as one TLS record, stopping `seconds` half-way through it."""
        wire = self.encrypt(data)
        with self.wire_lock:
            self.sock.sendall(wire[: len(wire) // 2])
            time.sleep(seconds)
            self.sock.sendall(wire[len(wire) // 2 :])

    def stall_between_records(self, data, seconds):
        """Send the 4-byte length as its own record, then the body after `seconds`."""
        head, body = self.encrypt(data[:4]), self.encrypt(data[4:])
        with self.wire_lock:
            self.sock.sendall(head)
            time.sleep(seconds)
            self.sock.sendall(body)

    def gaps(self, start, end):
        """The longest stretch in [start, end] with no frame from the client."""
        times = [start] + [t for t, _ in self.arrivals if start < t < end] + [end]
        return max(b - a for a, b in zip(times, times[1:]))

    def pings(self, start=0.0):
        return sum(1 for t, tag in self.arrivals if tag == 14 and t > start)


class Server:
    def __init__(self, key, certificate):
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(certificate, key)
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.port = self.listener.getsockname()[1]
        self.connections = []
        self.login_delay = 0.0
        self.accepted = threading.Condition()
        threading.Thread(target=self.accept, daemon=True).start()

    def accept(self):
        while True:
            sock, _ = self.listener.accept()
            with self.accepted:
                self.connections.append(Connection(sock, self.context, self.login_delay))
                self.accepted.notify_all()

    def connect(self, ca, account="tester"):
        """A peer and the server side of its connection."""
        count = len(self.connections)
        peer = Peer(self.port, account, "pw" if account else None, ca=ca, content="check")
        with self.accepted:
            assert self.accepted.wait_for(lambda: len(self.connections) > count, 5)
            return peer, self.connections[count]


def credentials(directory):
    """A throwaway CA and a localhost certificate it signs."""
    def openssl(*args):
        subprocess.run(["openssl", *args], check=True, capture_output=True)

    ca_key, ca, key, request, certificate = (
        directory / name for name in ("ca.key", "ca.pem", "server.key", "server.csr", "server.pem")
    )
    curve = ["-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes"]
    openssl("req", "-x509", *curve, "-keyout", ca_key, "-out", ca, "-days", "1",
            "-subj", "/CN=world_peer_check CA", "-addext", "basicConstraints=critical,CA:TRUE",
            "-addext", "keyUsage=critical,keyCertSign,cRLSign")
    openssl("req", *curve, "-keyout", key, "-out", request, "-subj", "/CN=localhost")
    extensions = directory / "server.ext"
    extensions.write_text("subjectAltName=DNS:localhost\nbasicConstraints=CA:FALSE\n"
                          "keyUsage=digitalSignature\nextendedKeyUsage=serverAuth\n")
    openssl("x509", "-req", "-in", request, "-CA", ca, "-CAkey", ca_key, "-CAcreateserial",
            "-out", certificate, "-days", "1", "-extfile", extensions)
    return key, certificate, ca


def expect_failure(peer, words):
    """The keepalive failure is raised by the next peer use, then cleared."""
    try:
        peer.send(14)
    except KeepaliveError as error:
        assert words in str(error), (words, str(error))
    else:
        raise AssertionError(("no KeepaliveError", words))
    world_peer._failure = None


def wait_for(condition, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


def check(directory):
    key, certificate, ca = credentials(directory)
    server = Server(key, certificate)

    # An idle logged-in peer is pinged within the deadline.
    peer, conn = server.connect(ca)
    start = time.monotonic()
    time.sleep(2.6)
    gap = conn.gaps(start, time.monotonic())
    assert gap < IDLE_GAP and conn.pings(start) >= 2, (gap, conn.pings(start))
    print(f"PASS idle peer pinged, longest silence {gap:.2f} s", flush=True)

    # A slow login is not lateness: the keepalive could not ping the peer before
    # it was tended, and the server restarts its read deadline after the reply.
    for delay in (1.8, 2.6):
        server.login_delay = delay
        slow, slow_conn = server.connect(ca)
        start = time.monotonic()
        time.sleep(1.5)
        assert world_peer._failure is None, (delay, world_peer._failure)
        assert slow_conn.pings(start) >= 1, delay
        slow.s.close()
        print(f"PASS a login answered after {delay} s is not counted late", flush=True)
    server.login_delay = 0.0

    # A receive waiting on a stalled frame does not stop the pings.
    for name, stall in [("inside a TLS record", conn.stall_in_record),
                        ("between the length and body records", conn.stall_between_records)]:
        result = {}
        reader = threading.Thread(target=lambda: result.update(got=peer.receive()))
        start = time.monotonic()
        sender = threading.Thread(target=stall, args=(frame(99, blob(1, name)), 2.5))
        sender.start()
        time.sleep(0.1)
        reader.start()
        sender.join()
        reader.join()
        gap = conn.gaps(start, time.monotonic())
        assert result["got"][0] == 99 and result["got"][1][1] == [name.encode()], result
        assert gap < IDLE_GAP, (name, gap)
        print(f"PASS frame stalled {name} for 2.5 s: pings continued "
              f"(longest silence {gap:.2f} s), frame intact", flush=True)

    # A frame not whole within the receive's 4 s is kept for the next receive.
    sender = threading.Thread(target=conn.stall_in_record, args=(frame(98, blob(1, b"late")), 4.6))
    sender.start()
    begun = time.monotonic()
    try:
        peer.receive()
        raise AssertionError("receive returned a frame still stalled")
    except TimeoutError:
        waited = time.monotonic() - begun
    sender.join()
    tag, data = peer.receive()
    assert 3.9 < waited < 4.5 and tag == 98 and data[1] == [b"late"], (waited, tag, data)
    print(f"PASS a frame stalled past the receive deadline timed out after {waited:.2f} s "
          "and arrived whole on the next receive", flush=True)

    # An error inside the keepalive loop: the thread survives, keeps pinging, and
    # the next peer use fails with the error.
    class Faulty(weakref.WeakSet):
        faults = 1

        def __iter__(self):
            if Faulty.faults:
                Faulty.faults -= 1
                raise RuntimeError("injected keepalive loop error")
            return super().__iter__()

    original = world_peer._tended
    faulty = Faulty()
    for p in list(original):
        faulty.add(p)
    world_peer._tended = faulty
    assert wait_for(lambda: Faulty.faults == 0, 2)
    start = time.monotonic()
    time.sleep(1.6)
    assert world_peer._tender.is_alive() and conn.pings(start) >= 1
    expect_failure(peer, "injected keepalive loop error")
    world_peer._tended = original
    print("PASS keepalive loop error: thread kept pinging, next peer use raised it", flush=True)

    # An unexpected error from one ping is reported the same way.
    writable = world_peer._writable
    raised = []

    def broken(s):
        world_peer._writable = writable
        raised.append(True)
        raise ValueError("injected ping error")

    world_peer._writable = broken
    assert wait_for(lambda: world_peer._failure is not None, 3) and raised
    assert not peer.keepalive  # set before the failure is recorded
    expect_failure(peer, "injected ping error")
    peer.tend()
    print("PASS unexpected ping error: next peer use raised it", flush=True)

    # A thread that dies is reported, and the next tended peer restarts it.
    class Fatal(weakref.WeakSet):
        def __iter__(self):
            raise SystemExit("injected keepalive thread exit")

    fatal = Fatal()
    for p in list(original):
        fatal.add(p)
    world_peer._tended = fatal
    dead = world_peer._tender
    assert wait_for(lambda: not dead.is_alive(), 2)
    world_peer._tended = original
    expect_failure(peer, "injected keepalive thread exit")
    try:
        peer.send(14)
        raise AssertionError("a dead keepalive thread was not reported")
    except KeepaliveError as error:
        assert "not running" in str(error), error
    peer.tend()  # the next tended peer restarts the thread
    assert world_peer._tender.is_alive() and world_peer._tender is not dead
    second, conn2 = server.connect(ca)
    start = time.monotonic()
    time.sleep(1.6)
    assert conn.pings(start) >= 1 and conn2.pings(start) >= 1
    print("PASS dead keepalive thread: next peer use raised it, next login restarted it", flush=True)

    # A thread starved past the server's deadline is a failure.
    with world_peer._tended_lock:  # the thread waits here, as a starved thread would
        time.sleep(2.4)
    assert wait_for(lambda: world_peer._failure is not None, 2)
    time.sleep(0.3)  # let the pass finish with the other peer before clearing
    expect_failure(peer, "without a frame")
    print("PASS keepalive starved past the deadline: next peer use raised it", flush=True)

    # A peer the test is using is not late however long it holds the peer.
    time.sleep(0.5)
    with second.lock:
        time.sleep(2.6)
    time.sleep(0.6)
    assert world_peer._failure is None, world_peer._failure
    print("PASS a peer held by the test for 2.6 s is not counted late", flush=True)

    # A peer the server closes stops being pinged, without a failure; the test
    # meets the disconnect on its next use.
    conn2.sock.shutdown(socket.SHUT_RDWR)
    conn2.sock.close()
    assert wait_for(lambda: not second.keepalive, 4), "keepalive kept pinging a closed peer"
    assert world_peer._failure is None, world_peer._failure
    try:
        second.receive()
        raise AssertionError("no disconnect")
    except DISCONNECTED:
        pass
    print("PASS a peer the server closed stopped being pinged without a failure", flush=True)

    # A peer the test closes stops being pinged, without a failure.
    third, conn3 = server.connect(ca)
    third.s.close()
    assert wait_for(lambda: not third.keepalive, 2)
    assert world_peer._failure is None, world_peer._failure
    print("PASS a peer the test closed stopped being pinged without a failure", flush=True)

    # A peer that never logged in is never pinged (the adverse-framing probes).
    probe, conn4 = server.connect(ca, account=None)
    start = time.monotonic()
    time.sleep(1.6)
    assert conn4.pings() == 0 and not probe.keepalive
    probe.s.close()
    print("PASS a peer that never logged in was not pinged", flush=True)

    # PQ-427: a route loop (pump(.05), then a move) pings at the keepalive
    # cadence. pump used to ping at the start of every call: 20 pings a second,
    # each a Redis write the server awaits in the session's read loop.
    router, conn5 = server.connect(ca)
    streaming = threading.Event()

    def stream():
        while not streaming.is_set():
            conn5.send(frame(10))  # an empty World, one a tick
            time.sleep(0.05)

    threading.Thread(target=stream, daemon=True).start()
    start = time.monotonic()
    loops = 0
    while time.monotonic() - start < 3:
        router.pump(.05)
        router.send(9)  # a move, as run() sends one after each pump
        loops += 1
    streaming.set()
    pings = conn5.pings(start)
    allowed = int(3 / world_peer.KEEPALIVE) + 1
    assert loops >= 30 and 3 <= pings <= allowed, (loops, pings, allowed)
    print(f"PASS a route loop of {loops} pump(.05) calls and moves sent {pings} pings in 3 s "
          f"(at most {allowed}: one per {world_peer.KEEPALIVE} s)", flush=True)

    # PQ-427: the server's Error and LoggedOut before it closes are named in the
    # EOF, though the test's until(10) dropped them.
    time.sleep(0.1)
    conn5.send(frame(4, integer(1, 4) + blob(2, "session rate limit")))
    for _ in range(6):  # repeats are counted, not let push the rest out
        conn5.send(frame(4, integer(1, 4) + blob(2, "one movement per tick") + integer(3, 9)))
    conn5.send(frame(13))
    time.sleep(0.1)
    conn5.sock.shutdown(socket.SHUT_WR)  # the stream's end, as the server's close sends it
    try:
        router.pump(1)
        raise AssertionError("no disconnect")
    except EOFError as error:
        text = str(error)
    conn5.sock.close()
    assert text.startswith("closed ") and "Error code 4 'session rate limit' (request 0)" in text \
        and "Error code 4 'one movement per tick' (request 9) x6" in text and "LoggedOut" in text, text
    print(f"PASS a peer closed after an Error and LoggedOut it did not wait for met: EOFError({text!r})",
          flush=True)

    for p in (peer, second):
        p.s.close()


def child_failure():
    """A failure the test never meets still makes the process fail."""
    world_peer._fail("injected unreported failure")
    sys.exit(0)


def main():
    if sys.argv[1:] == ["child-failure"]:
        child_failure()
        return
    # The injected failures print their FAIL lines to stderr; keep them out of the
    # log and count them instead.
    printed = io.StringIO()
    try:
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(printed):
            check(Path(directory))
    except BaseException:
        sys.stderr.write(printed.getvalue())
        raise
    lines = printed.getvalue().count("FAIL peer keepalive:")
    assert lines == 4, printed.getvalue()
    print("PASS each injected failure printed one FAIL peer keepalive line", flush=True)
    result = subprocess.run([sys.executable, str(HERE), "child-failure"],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 1 and "FAIL peer keepalive" in result.stderr, (
        result.returncode, result.stderr)
    print("PASS an unreported keepalive failure makes the process exit 1", flush=True)
    assert world_peer._failure is None
    print("PASS world_peer keepalive checks", flush=True)


if __name__ == "__main__":
    main()
