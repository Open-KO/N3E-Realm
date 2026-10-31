"""Small dependency-free headless TLS/Protobuf peer; also used by acceptance tests."""

import argparse
import atexit
import collections
import errno
import hashlib
import os
import select
import socket
import ssl
import struct
import sys
import threading
import time
import traceback
import weakref

# A logged-in peer pings when it has sent nothing for KEEPALIVE seconds, as the real
# client does every second (client/network/world.cpp). The server drops a peer that
# sends no frame for two seconds (DEADLINE, server/src/network.rs), so a peer the
# test leaves idle while it works elsewhere (other peers, SQL, docker, sleeps) would
# otherwise be disconnected under load (PQ-112, PQ-119).
KEEPALIVE = 0.75
# How often the keepalive thread looks at the tended peers.
WAKE = 0.25
# The server's read deadline (DEADLINE in server/src/network.rs). A tended peer that
# the thread was free to ping but did not for this long may already be closed by the
# server, so the keepalive has failed (PQ-120).
DEADLINE = 2.0
# What a peer meets when the server process exits or drops the connection, the
# disconnect a crash test expects (PQ-126): the read finds the stream's end
# (EOFError from _frame; ssl's SSLEOFError or SSLZeroReturnError when TLS ends
# without or with close_notify) or the kernel resets it (ConnectionError covers
# ConnectionResetError and, on a send, BrokenPipeError). Never bare OSError: the
# receive deadline is a TimeoutError, an OSError too, and a server that stays up
# but silent must fail the test, not count as the crash it was meant to show.
DISCONNECTED = (EOFError, ConnectionError, ssl.SSLEOFError, ssl.SSLZeroReturnError)
_tended = weakref.WeakSet()
_tended_lock = threading.Lock()
_tender = None
# The first keepalive failure, as text. Once set, every later peer use raises it
# and the process cannot exit 0 (_report), so a stopped or failing keepalive fails
# the suite with this message instead of letting idle peers drop silently (PQ-120).
_failure = None


class KeepaliveError(RuntimeError):
    """The keepalive thread stopped or failed, so idle peers may have been dropped."""


def _fail(text):
    global _failure
    with _tended_lock:
        first_failure = _failure is None
        if first_failure:
            _failure = text
    if first_failure:
        print("FAIL peer keepalive:", text, file=sys.stderr, flush=True)


def _check():
    """Raise in the test's own thread if the keepalive failed or is not running."""
    if _failure is not None:
        raise KeepaliveError(_failure)
    tender = _tender
    if tender is not None and not tender.is_alive():
        raise KeepaliveError("the peer keepalive thread is not running")


@atexit.register
def _report():
    # A failure the test never met (it came after the last peer use, or the test
    # swallowed the KeepaliveError) still fails the process. A process already
    # failing with its own uncaught error keeps it; the FAIL line is printed.
    if _failure is None or hasattr(sys, "last_exc"):
        return
    print("FAIL peer keepalive (exit status 1):", _failure, file=sys.stderr, flush=True)
    sys.stdout.flush()
    os._exit(1)


def _writable(s):
    poll = select.poll()
    poll.register(s.fileno(), select.POLLOUT)
    return bool(poll.poll(0))


def _ping(p, now):
    """Ping one tended peer if it is due. The caller holds p.lock."""
    if not p.keepalive:
        return
    if p.s.fileno() < 0:
        p.keepalive = False  # closed by the test
        return
    if now - p.last < KEEPALIVE:
        return
    if not _writable(p.s):
        # The server is not reading this connection. A ping would block the thread,
        # and every other peer's pings with it, for the 4 s socket timeout.
        p.excused = now
        return
    late = now - max(p.last, p.excused)
    if late >= DEADLINE:
        _fail(
            f"a logged-in peer went {late:.2f} s without a frame while the keepalive "
            f"was free to ping it (server deadline {DEADLINE} s); the keepalive thread "
            "was starved or stopped"
        )
    try:
        p._write(blob(14, b""))
    except DISCONNECTED:
        pass  # the server closed it; _write stopped its keepalive and the test sees it


def _tend():
    try:
        while True:
            time.sleep(WAKE)
            try:
                with _tended_lock:
                    peers = list(_tended)
            except Exception:
                _fail("keepalive pass failed:\n" + traceback.format_exc())
                continue
            for p in peers:
                if not p.lock.acquire(False):
                    # In use by the test right now (a send, a frame being read, logout):
                    # not idle on the keepalive's account.
                    p.excused = time.monotonic()
                    continue
                try:
                    _ping(p, time.monotonic())
                except Exception:
                    p.keepalive = False
                    _fail("keepalive ping failed:\n" + traceback.format_exc())
                finally:
                    p.lock.release()
    except BaseException:
        _fail("the peer keepalive thread stopped:\n" + traceback.format_exc())
        raise


class _Guarded:
    """The peer's TLS socket. Every use holds the peer's lock, so the keepalive
    thread never uses the socket at the same time as the test, and a test's direct
    `peer.s` calls (close, sendall, recv, pending) stay safe. Peer.receive holds the
    lock only for reads that cannot block (PQ-120)."""

    def __init__(self, s, lock):
        self._s, self._lock = s, lock

    def __getattr__(self, name):
        return getattr(self._s, name)

    def sendall(self, b):
        with self._lock:
            return self._s.sendall(b)

    def recv(self, n):
        with self._lock:
            return self._s.recv(n)

    def pending(self):
        with self._lock:
            return self._s.pending()

    def close(self):
        with self._lock:
            return self._s.close()


def varint(n):
    b = bytearray()
    while n > 127:
        b.append((n & 127) | 128)
        n >>= 7
    return bytes(b) + bytes([n])


def integer(tag, n):
    return varint(tag << 3) + varint(n)


def blob(tag, b):
    if isinstance(b, str):
        b = b.encode()
    return varint(tag << 3 | 2) + varint(len(b)) + b


# A Ping envelope (Envelope.ping, field 14): _write notes when one was sent.
PING = blob(14, b"")


def real(tag, x):
    return varint(tag << 3 | 5) + struct.pack("<f", x)


def fields(b):
    p = 0
    result = {}

    def vint():
        nonlocal p
        n = 0
        for shift in range(0, 70, 7):
            x = b[p]
            p += 1
            n |= (x & 127) << shift
            if x < 128:
                return n
        raise ValueError("varint bound")

    while p < len(b):
        key = vint()
        kind = key & 7
        if kind == 0:
            value = vint()
        elif kind == 2:
            n = vint()
            value = b[p : p + n]
            p += n
        elif kind == 5:
            value = struct.unpack("<f", b[p : p + 4])[0]
            p += 4
        elif kind == 1:
            value = b[p : p + 8]
            p += 8
        else:
            raise ValueError("unsupported wire kind")
        result.setdefault(key >> 3, []).append(value)
    return result


def first(f, tag, default=0):
    return f.get(tag, [default])[0]


class Budget:
    """Load-independent bound for a fight whose outcome rests on hit rolls (PQ-123).

    The server rolls every strike, and machine load stretches how long walking and
    pacing take in wall time, so a fight bounded by elapsed time fails at random
    when the rolls run cold or the harness runs slow (stats_live, PQ-123). A Budget
    fails only after `strikes` resolved attack attempts (hit or miss), `steps`
    approach moves or `replies` other action results (cooldown, out of range), so
    the chance of a spurious failure is set by the fixture's hit rate and `strikes`
    alone: choose `strikes` from that rate (evidence pq-123, Attempt 3). `guard`
    seconds only catches a stalled server or harness; it must stay far above what
    the counts take under load and is never the bound a fight is expected to meet.
    """

    RESOLVED = ("hit", "miss")

    def __init__(self, what, strikes, steps=600, replies=3000, guard=120):
        self.what = what
        self.left = {"strike": strikes, "step": steps, "reply": replies}
        self.end = time.monotonic() + guard
        self.last = "none"

    def spend(self, kind, *context):
        self.left[kind] -= 1
        if self.left[kind] < 0:
            raise AssertionError((self.what, kind + " budget spent", self.last, *context))

    def step(self, *context):
        """One approach move."""
        self.spend("step", *context)

    def result(self, status, *context):
        """One action result; returns the status as text."""
        if isinstance(status, bytes):
            status = status.decode()
        self.last = status
        self.spend("strike" if status in self.RESOLVED else "reply", *context)
        return status

    def ok(self, *context):
        """Loop condition: True until the stall guard trips, then fail."""
        if time.monotonic() > self.end:
            raise AssertionError((self.what, "stall guard", self.last, self.left, *context))
        return True


class Peer:
    def __init__(
        self,
        port,
        account=None,
        password=None,
        ca="deploy/local/ca.pem",
        content=None,
        receive_buffer=None,
        game="demo",
        protocol=1,
        source=None,
    ):
        context = ssl.create_default_context(cafile=ca)
        raw = socket.socket()
        raw.settimeout(4)
        if receive_buffer:
            raw.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, receive_buffer)
        if source:
            # Another loopback address (127.0.0.0/8): the server's per-address
            # login limit then counts this peer apart (PQ-250).
            raw.bind((source, 0))
        raw.connect(("127.0.0.1", port))
        self.lock = threading.RLock()
        self.keepalive = False
        self.last = time.monotonic()
        self.excused = 0.0  # last time the keepalive found this peer busy (_ping)
        self.pinged = 0.0  # last ping sent, by pump or the keepalive (PQ-427)
        self.received = time.monotonic()  # when the last whole frame arrived
        # The last kinds of Error and LoggedOut frames, whether or not the test
        # waited for them: until() drops a frame it was not asked for, so a server
        # that refused or ended the session before closing it left only an EOF
        # (PQ-427). Text -> (count, last arrival); a repeated one moves to the end.
        self.notices = collections.OrderedDict()
        self._reader = threading.RLock()  # one frame reader at a time
        self._rx = bytearray()  # the part of the next frame read so far
        self.s = _Guarded(context.wrap_socket(raw, server_hostname="localhost"), self.lock)
        self.protocol = protocol
        self.session = self.id = self.seq = 0
        self.entities = {}
        self.characters = []
        self.inventory = {}
        self.action_seq = 0
        self.action_id = ""
        self.content = (
            content or open("build/packages/legacy-demo/release.sha256").read().strip()
        )
        self.send(1, integer(1, protocol) + blob(2, game) + blob(3, self.content))
        tag, data = self.receive()
        # A refusal is an Error (tag 4): name its code and detail (PQ-368).
        assert tag == 3, ("handshake rejected", tag, first(data, 1), first(data, 2, b""))
        if account is not None:
            self.send(5, blob(1, account) + blob(2, password))
            tag, data = self.until(6, 4)
            assert tag == 6, ("login", data)
            self.tend()

    def tend(self):
        """Keep this peer alive from now on (logged-in peers do so automatically)."""
        global _tender
        with self.lock:
            # The lateness clock (_ping) starts here, not at the last frame sent:
            # before now the keepalive could not ping this peer. Login is the case:
            # the server handles it inline (scrypt, database) and restarts its read
            # deadline only after the reply, so a slow login put no peer at risk.
            self.excused = time.monotonic()
            self.keepalive = True
        with _tended_lock:
            _tended.add(self)
            # A thread that died has recorded its failure (_tend), so a restart
            # keeps later peers alive without hiding it.
            if _tender is None or not _tender.is_alive():
                _tender = threading.Thread(target=_tend, name="peer-keepalive", daemon=True)
                _tender.start()

    def send(self, tag, data=b""):
        self.raw(blob(tag, data))

    def raw(self, b):
        _check()
        self._write(b)

    def _write(self, b):
        with self.lock:
            try:
                self.s.sendall(struct.pack(">I", len(b)) + b)
            except BaseException:
                self.keepalive = False  # a failed or partial send leaves no usable stream
                raise
            self.last = time.monotonic()
            if b == PING:
                self.pinged = self.last

    def receive(self):
        # The lock is held only for reads that cannot block: waiting for a frame, or
        # for the rest of one stalled inside a TLS record, happens without it, so the
        # keepalive thread can ping this peer meanwhile (PQ-120). A frame not whole
        # within 4 s raises TimeoutError and keeps what arrived for the next call.
        _check()
        deadline = time.monotonic() + 4
        with self._reader:
            while True:
                if self.s.fileno() < 0:
                    raise OSError(errno.EBADF, "peer socket closed")
                try:
                    frame = self._take()
                except BaseException:
                    self.keepalive = False  # the stream ended or is corrupt
                    raise
                if frame is not None:
                    return self._parse(frame)
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError("timed out")
                select.select([self.s], [], [], left)

    def _take(self):
        """The next frame's envelope once it has arrived whole, else None. Reads what
        has arrived, never past the frame, so `s.pending()` still shows the rest."""
        with self.lock:
            while True:
                have = len(self._rx)
                if have < 4:
                    need = 4 - have
                else:
                    n = struct.unpack(">I", self._rx[:4])[0]
                    assert 0 < n <= 65536
                    need = 4 + n - have
                    if need == 0:
                        frame = bytes(self._rx[4:])
                        self._rx.clear()
                        self.received = time.monotonic()
                        return frame
                part = self._available(need)
                if part is None:
                    return None
                if not part:
                    raise EOFError(self._closed())
                self._rx += part

    def _closed(self):
        """The EOF's text: "closed", then how long after the last whole frame,
        and the last Error or LoggedOut frames the server sent (PQ-427)."""
        now = time.monotonic()
        text = f"closed {now - self.received:.2f} s after the last whole frame"
        if self.notices:
            text += "; the server's last notices: " + ", ".join(
                f"{what}{f' x{n}' if n > 1 else ''} {now - at:.2f} s before"
                for what, (n, at) in self.notices.items())
        return text

    def _notice(self, what):
        n, _ = self.notices.pop(what, (0, 0.0))
        self.notices[what] = (n + 1, time.monotonic())
        while len(self.notices) > 4:
            self.notices.popitem(last=False)

    def _available(self, n):
        """Up to n bytes the connection already holds, b"" at its end, None if none
        yet. The TLS socket is non-blocking for the call, so a partial TLS record
        returns None instead of waiting for the rest under the lock."""
        s = self.s._s
        timeout = s.gettimeout()
        s.settimeout(0)
        try:
            return s.recv(n)
        except (ssl.SSLWantReadError, ssl.SSLWantWriteError, BlockingIOError):
            return None
        finally:
            s.settimeout(timeout)

    def _parse(self, envelope):
        e = fields(envelope)
        tag = next(iter(e))
        data = fields(e[tag][0])
        if tag == 4:
            detail = first(data, 2, b"").decode(errors="replace")
            self._notice(f"Error code {first(data, 1)} {detail!r} (request {first(data, 3)})")
        elif tag == 13:
            self._notice("LoggedOut")
        if tag == 6:
            self.characters = [
                (first(fields(c), 1), first(fields(c), 2, b"").decode())
                for c in data.get(1, [])
            ]
        if tag == 10:
            self.inventory = fields(first(data, 5, b""))
            self.action_id = first(data, 6, b"").decode()
            self.session = first(data, 2)
            self.id = first(data, 3)
            self.tick = first(data, 1)
            self.entities = {first(fields(e), 1): fields(e) for e in data.get(4, [])}
        return tag, data

    def until(self, *tags, seconds=4):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            tag, data = self.receive()
            if tag in tags:
                return tag, data
        raise TimeoutError(tags)

    def create(self, name):
        self.send(7, blob(1, name))
        tag, data = self.until(6, 4)
        assert tag == 6, data
        return next(i for i, n in self.characters if n == name)

    def select(self, id):
        self.send(8, integer(1, id))
        return self.until(10, 4)

    def action(self, target, seq=None, session=None, action=None):
        self.action_seq = self.action_seq + 1 if seq is None else seq
        self.send(
            15,
            integer(1, self.session if session is None else session)
            + integer(2, self.action_seq)
            + integer(3, target)
            + blob(4, self.action_id if action is None else action),
        )
        tag, data = self.until(16, 4)
        assert tag == 16, data
        return first(data, 2, b"").decode()

    def move(self, x, z, seq=None, session=None, mode=0):
        self.seq = self.seq + 1 if seq is None else seq
        self.send(
            9,
            integer(1, self.session if session is None else session)
            + integer(2, self.seq)
            + real(3, x)
            + real(4, z)
            + integer(5, mode)
            + (integer(7, self.id) if self.protocol >= 7 else b""),
        )

    def pump(self, seconds=0.2):
        # A ping when KEEPALIVE has passed since the last one, as the real client
        # pings once a second (client/network/world.cpp). It used to ping at the
        # start of every call, so a loop of pump(.05) sent 20 pings a second, each
        # a Redis presence write the server awaits in the session's read loop,
        # beside the loop's moves (PQ-427).
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if time.monotonic() - self.pinged >= KEEPALIVE:
                self.send(14)
            self.until(10)

    def logout(self):
        # No ping may follow the logout: the server stops reading at Logout, and a
        # frame it never reads makes its close a reset that can discard LoggedOut.
        with self.lock:
            self.keepalive = False
            self.send(12)
        self.until(13)
        self.s.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=7777)
    p.add_argument("--account", required=True)
    p.add_argument("--create")
    p.add_argument("--select", type=int)
    p.add_argument("--seconds", type=float, default=3)
    a = p.parse_args()
    peer = Peer(a.port, a.account, os.environ["N3E_PASSWORD"])
    if a.create:
        peer.create(a.create)
    print("characters:", peer.characters)
    if a.select:
        assert peer.select(a.select)[0] == 10
        peer.pump(a.seconds)
        print("tick:", peer.tick, "entities:", peer.entities)
    peer.logout()
