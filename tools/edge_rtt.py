"""Round trip and connect time of a realm's game wire, direct or through its edge (spec 12).

  python3 tools/edge_rtt.py run (--edge wss://HOST/PATH | --direct HOST:PORT) --host NAME
        (--manifest URL | --package DIR | --game G --content HASH --protocol N)
        [--ca PEM] [--rate HZ] [--minutes M] [--session-secs S] [--every S] --out FILE.jsonl
  python3 tools/edge_rtt.py connects (--edge … | --direct …) --host NAME (identity as above)
        [--ca PEM] [--count N] [--every S] --out FILE.jsonl
  python3 tools/edge_rtt.py summary FILE.jsonl… [--icmp NAME=PING_OUTPUT]…

A measuring tool beside the client: it speaks the client's transport (the WebSocket and
inner TLS of client/network/websocket.cpp and world.cpp, or plain TCP and TLS with
--direct), sends the client's Handshake and then, without logging in, times what the
server already answers:

- echo: an empty `Input` envelope before login. The server answers every message it does
  not handle before login with `Error{code: UNAUTHENTICATED}` (server/src/network.rs),
  so this is a round trip through the whole path to the server's connection task (not
  its tick). It needs no account, token or server change; the game server logs nothing
  for it, and `realm-edge` still writes its one line per connection (spec 12).
- wsping: a WebSocket ping, answered by `realm-edge` on the realm's host (spec 12).
- connect: DNS, TCP, outer TLS and the WebSocket upgrade (`realm-edge` connects to the
  server before its 101), the inner TLS, and Handshake to its Snapshot. Login to
  Characters needs an account, so it is not here; a logged-in client logs it, and its
  own round trip, itself (spec 12, "The client's round trip").

--rate 1 is the client's 1 s Ping cadence ("idle"); --rate 20 its 20 Hz Move cadence in
the world ("moving": the upstream rate, not the World snapshots the server sends back).
Sessions last --session-secs, then reconnect after --every seconds; `connects` opens
--count connections --every seconds apart. Spec 01 allows 10 connects a minute and three
open sockets per source; this tool holds one socket and connects at most once every 7 s.
Every wait is bounded; three failed connects in a row end the run.

Records are JSON lines (no addresses); `summary` prints median, p95, p99 and the worst
for each path and rate, and the worst gap between the server's replies; --icmp adds a
`ping -D -O -i 1` baseline (to the edge, or to the realm's host where its game port is
not reachable, as spec 12's host keeps it on loopback). Keep raw output
under build/ (git-ignored). Method and figures: spec 12, "Measured round trip".
"""
import argparse
import base64
import hashlib
import json
import os
import pathlib
import re
import select
import socket
import ssl
import struct
import sys
import time
import urllib.parse
import urllib.request

PROTOCOL = "n3e-wire.1"  # spec 12
MAX_FRAME = 64 * 1024 + 1024  # spec 12: the largest WebSocket frame either side accepts
MAX_MESSAGE = 65536  # the game wire's frame bound
MAX_HEAD = 8 * 1024
CONNECT_DEADLINE = 7.0  # the client's outer handshake deadline (world.cpp)
INNER_DEADLINE = 2.0  # spec 01, N3E_PREAUTH_IDLE_MS
REPLY_DEADLINE = 5.0  # an echo unanswered this long ends the session
MIN_CONNECT_SPACING = 7.0  # under spec 01's 10 connects per 60 s
MAX_OUTSTANDING = 64
UNAUTHENTICATED = 5
now = time.perf_counter


class Failed(Exception):
    def __init__(self, phase, detail):
        super().__init__(f"{phase}: {detail}")
        self.phase, self.detail = phase, detail


# Protobuf, the few fields this tool reads and writes (protocol/wire.proto).
def varint(n):
    out = bytearray()
    while True:
        b, n = n & 0x7F, n >> 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def field(number, payload):
    return varint(number << 3 | 2) + varint(len(payload)) + payload


def fields(b):
    """(field number, wire type, value) of one message; values of type 2 are bytes."""
    i = 0
    while i < len(b):
        key, i = read_varint(b, i)
        kind = key & 7
        if kind == 0:
            value, i = read_varint(b, i)
        elif kind == 2:
            n, i = read_varint(b, i)
            value, i = b[i : i + n], i + n
        elif kind == 5:
            value, i = b[i : i + 4], i + 4
        elif kind == 1:
            value, i = b[i : i + 8], i + 8
        else:
            raise Failed("decode", f"wire type {kind}")
        yield key >> 3, kind, value


def read_varint(b, i):
    n = shift = 0
    while True:
        if i >= len(b) or shift > 63:
            raise Failed("decode", "truncated varint")
        n |= (b[i] & 0x7F) << shift
        shift += 7
        i += 1
        if not b[i - 1] & 0x80:
            return n, i


def handshake(identity):
    body = varint(1 << 3) + varint(identity["protocol"])
    body += field(2, identity["game"].encode()) + field(3, identity["content"].encode())
    return field(1, body)  # Envelope.handshake


ECHO = field(2, b"")  # Envelope.input, empty: not handled before login


def envelope(b):
    """The body's field number and, for an Error, its code."""
    for number, kind, value in fields(b):
        if kind == 2:
            code = None
            if number == 4:
                code = next((v for n, k, v in fields(value) if n == 1 and k == 0), 0)
            return number, code
    return 0, None


# The realm's identity for the Handshake: game, content hash, protocol (spec 04).
def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "n3e-edge-rtt"})
    with urllib.request.urlopen(request, timeout=15) as r:
        return r.read(16 * 1024 * 1024 + 1)


def release_identity(release, expect=None):
    if release[:4] != b"N3R1" or len(release) < 20:
        raise SystemExit("release.bin: not an N3R1 index")
    protocol = struct.unpack_from("<I", release, 12)[0]
    n = struct.unpack_from("<I", release, 16)[0]
    game = release[20 : 20 + n].decode()
    content = hashlib.sha256(release).hexdigest()
    if expect and content != expect:
        raise SystemExit("release.bin does not match the manifest's content.hash")
    return {"game": game, "content": content, "protocol": protocol}


def identity(a):
    if a.manifest:
        m = json.loads(fetch(a.manifest))
        c = m["content"]
        index = json.loads(fetch(c["index_url"]))
        entry = next(f for f in index["files"] if f["path"] == "release.bin")
        return release_identity(fetch(c["base_url"] + entry["sha256"]), c["hash"])
    if a.package:
        return release_identity(pathlib.Path(a.package, "release.bin").read_bytes())
    if a.game and a.content and a.protocol is not None:
        return {"game": a.game, "content": a.content, "protocol": a.protocol}
    raise SystemExit("name the realm's release: --manifest, --package or --game/--content/--protocol")


# Carriers: the bytes of the inner TLS stream, over a WebSocket or a TCP socket.
def remaining(deadline):
    left = deadline - now()
    if left <= 0:
        raise TimeoutError
    return left


def readable(sock, deadline):
    if isinstance(sock, ssl.SSLSocket) and sock.pending():
        return True
    return bool(select.select([sock], [], [], max(0.0, deadline - now()))[0])


def tcp(host, port, timings):
    t = now()
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as e:
        raise Failed("dns", type(e).__name__)
    timings["dns_ms"] = ms(now() - t)
    t = now()
    last = None
    for family, kind, proto, _, address in addresses:
        s = socket.socket(family, kind, proto)
        s.settimeout(CONNECT_DEADLINE)
        try:
            s.connect(address)
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            timings["tcp_ms"] = ms(now() - t)
            return s
        except OSError as e:
            last = e
            s.close()
    raise Failed("tcp", type(last).__name__ if last else "no address")


class Direct:
    def __init__(self, endpoint, timings):
        host, _, port = endpoint.rpartition(":")
        self.sock = tcp(host, int(port), timings)

    def send(self, data, deadline):
        self.sock.settimeout(remaining(deadline))
        self.sock.sendall(data)

    def receive(self, deadline):
        """(inner bytes, pongs): what one read brought, ([], []) when nothing came."""
        if not readable(self.sock, deadline):
            return b"", []
        b = self.sock.recv(65536)
        if not b:
            raise Failed("closed", "by the peer")
        return b, []

    def ping(self, payload, deadline):
        pass

    def close(self):
        self.sock.close()


class Edge:
    def __init__(self, url, timings, ca):
        u = urllib.parse.urlsplit(url)
        if u.scheme != "wss" or not u.hostname:
            raise SystemExit("the edge must be wss://HOST[:PORT]/PATH")
        port = u.port or 443
        raw = tcp(u.hostname, port, timings)
        t = now()
        context = ssl.create_default_context(cafile=ca)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        raw.settimeout(CONNECT_DEADLINE)
        try:
            self.sock = context.wrap_socket(raw, server_hostname=u.hostname)
        except (OSError, ssl.SSLError) as e:
            raw.close()
            raise Failed("outer_tls", type(e).__name__)
        timings["tls_ms"] = ms(now() - t)
        try:
            self.upgrade(u, port, timings)
        except BaseException:
            self.sock.close()
            raise

    def upgrade(self, u, port, timings):
        t = now()
        key = base64.b64encode(os.urandom(16)).decode()
        authority = u.hostname if port == 443 else f"{u.hostname}:{port}"
        request = (
            f"GET {u.path or '/'} HTTP/1.1\r\nHost: {authority}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
            f"Sec-WebSocket-Protocol: {PROTOCOL}\r\nUser-Agent: n3e-edge-rtt\r\n\r\n"
        )
        self.sock.sendall(request.encode())
        self.rx = b""
        deadline = t + CONNECT_DEADLINE
        while b"\r\n\r\n" not in self.rx:
            if len(self.rx) > MAX_HEAD or not readable(self.sock, deadline):
                raise Failed("upgrade", "no response head")
            b = self.sock.recv(4096)
            if not b:
                raise Failed("upgrade", "closed")
            self.rx += b
        head, self.rx = self.rx.split(b"\r\n\r\n", 1)
        lines = head.decode("latin-1").split("\r\n")
        if not lines[0].startswith("HTTP/1.1 101 "):
            raise Failed("upgrade", lines[0][:40])
        headers = {k.strip().lower(): v.strip() for k, _, v in (h.partition(":") for h in lines[1:])}
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
        if headers.get("sec-websocket-accept") != accept.decode() or headers.get("sec-websocket-protocol") != PROTOCOL:
            raise Failed("upgrade", "bad accept or subprotocol")
        timings["upgrade_ms"] = ms(now() - t)
        self.fragments = None

    def frame(self, opcode, payload, deadline):
        n = len(payload)
        head = bytes([0x80 | opcode])
        if n < 126:
            head += bytes([0x80 | n])
        elif n <= 0xFFFF:
            head += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            head += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        body = bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
        self.sock.settimeout(remaining(deadline))
        self.sock.sendall(head + mask + body)

    def send(self, data, deadline):
        self.frame(0x2, data, deadline)

    def ping(self, payload, deadline):
        self.frame(0x9, payload, deadline)

    def frames(self):
        """Complete frames in rx, as (opcode, payload); the server's frames are unmasked."""
        out = []
        while len(self.rx) >= 2:
            b0, b1 = self.rx[0], self.rx[1]
            n, at = b1 & 0x7F, 2
            if b1 & 0x80:
                raise Failed("frame", "masked frame from the edge")
            if n == 126:
                if len(self.rx) < 4:
                    break
                n, at = struct.unpack_from(">H", self.rx, 2)[0], 4
            elif n == 127:
                if len(self.rx) < 10:
                    break
                n, at = struct.unpack_from(">Q", self.rx, 2)[0], 10
            if n > MAX_FRAME:
                raise Failed("frame", "oversize")
            if len(self.rx) < at + n:
                break
            out.append((b0 & 0x0F, b0 & 0x80, self.rx[at : at + n]))
            self.rx = self.rx[at + n :]
        return out

    def receive(self, deadline):
        if not self.frames_ready() and not readable(self.sock, deadline):
            return b"", []
        if not self.frames_ready():
            b = self.sock.recv(65536)
            if not b:
                raise Failed("closed", "by the edge")
            self.rx += b
        data, pongs = b"", []
        for opcode, _, payload in self.frames():
            if opcode in (0x0, 0x2):
                data += payload
            elif opcode == 0x9:
                self.frame(0xA, payload, now() + 2)
            elif opcode == 0xA:
                pongs.append(payload)
            elif opcode == 0x8:
                code = struct.unpack(">H", payload[:2])[0] if len(payload) >= 2 else 1005
                raise Failed("closed", f"WebSocket close {code}")
            else:
                raise Failed("frame", f"opcode {opcode}")
        return data, pongs

    def frames_ready(self):
        if len(self.rx) < 2:
            return False
        n, at = self.rx[1] & 0x7F, 2
        if n == 126:
            if len(self.rx) < 4:
                return False
            n, at = struct.unpack_from(">H", self.rx, 2)[0], 4
        elif n == 127:
            if len(self.rx) < 10:
                return False
            n, at = struct.unpack_from(">Q", self.rx, 2)[0], 10
        return len(self.rx) >= at + n

    def close(self):
        try:
            self.frame(0x8, struct.pack(">H", 1000), now() + 1)
        except (OSError, TimeoutError):
            pass
        self.sock.close()


class Session:
    """The inner TLS and the game wire over a carrier."""

    def __init__(self, a, ident):
        self.timings = {}
        start = now()
        self.carrier = Edge(a.edge, self.timings, a.ca) if a.edge else Direct(a.direct, self.timings)
        self.pongs = []
        try:
            t = now()
            context = ssl.create_default_context(cafile=a.ca)
            self.incoming, self.outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
            self.tls = context.wrap_bio(self.incoming, self.outgoing, server_hostname=a.host)
            deadline = t + INNER_DEADLINE
            while True:
                try:
                    self.tls.do_handshake()
                    break
                except ssl.SSLWantReadError:
                    self.flush(deadline)
                    self.pump(deadline)
            self.flush(deadline)
            self.timings["inner_tls_ms"] = ms(now() - t)
            t = now()
            self.app = b""
            self.write(handshake(ident), t + INNER_DEADLINE)
            number, code = self.message(t + INNER_DEADLINE)
            if number != 3:
                raise Failed("handshake", f"reply field {number} code {code}")
            self.timings["handshake_ms"] = ms(now() - t)
            self.timings["total_ms"] = ms(now() - start)
        except TimeoutError:
            self.carrier.close()
            raise Failed("inner", "deadline")
        except ssl.SSLError as e:
            self.carrier.close()
            raise Failed("inner_tls", type(e).__name__)
        except Failed:
            self.carrier.close()
            raise

    def flush(self, deadline):
        data = self.outgoing.read()
        if data:
            self.carrier.send(data, deadline)

    def pump(self, deadline):
        """One read from the carrier; False when nothing came by the deadline."""
        data, pongs = self.carrier.receive(deadline)
        self.pongs += [(now(), p) for p in pongs]
        if data:
            self.incoming.write(data)
        if not data and not pongs and now() >= deadline:
            raise TimeoutError
        return bool(data or pongs)

    def write(self, body, deadline):
        self.tls.write(struct.pack(">I", len(body)) + body)
        self.flush(deadline)

    def messages(self):
        while True:
            try:
                self.app += self.tls.read(65536)
            except ssl.SSLWantReadError:
                break
            except ssl.SSLZeroReturnError:
                raise Failed("closed", "TLS close")
        out = []
        while len(self.app) >= 4:
            n = struct.unpack_from(">I", self.app)[0]
            if n == 0 or n > MAX_MESSAGE:
                raise Failed("frame", "game-wire frame bound")
            if len(self.app) < 4 + n:
                break
            out.append(envelope(self.app[4 : 4 + n]))
            self.app = self.app[4 + n :]
        return out

    def message(self, deadline):
        while True:
            got = self.messages()
            if got:
                return got[0]
            self.pump(deadline)


def ms(seconds):
    return round(seconds * 1000, 3)


def path_name(a):
    return "edge" if a.edge else "direct"


def emit(out, record):
    record["at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    out.write(json.dumps(record) + "\n")
    out.flush()


def session(a, ident, out, number, end):
    s = Session(a, ident)
    emit(out, {"kind": "connect", "path": path_name(a), "session": number, **s.timings})
    interval = 1.0 / a.rate
    stop = min(end, now() + a.session_secs)
    outstanding, pings = [], {}
    next_echo, next_ping, counter = now(), now() + 0.5, 0
    last_reply, worst_gap, echoes = None, 0.0, 0
    reason = "session end"
    try:
        while now() < stop:
            t = now()
            if t >= next_echo:
                if len(outstanding) >= MAX_OUTSTANDING:
                    raise Failed("stall", "too many echoes outstanding")
                outstanding.append(t)
                s.write(ECHO, t + 2)
                next_echo += interval
                if next_echo <= t:
                    next_echo = t + interval
            if a.edge and t >= next_ping:
                counter += 1
                payload = struct.pack(">Q", counter)
                pings[payload] = t
                s.carrier.ping(payload, t + 2)
                next_ping = t + 1.0
                for old in [p for p, at in pings.items() if t - at > REPLY_DEADLINE]:
                    del pings[old]
            if outstanding and now() - outstanding[0] > REPLY_DEADLINE:
                raise Failed("stall", f"no reply in {REPLY_DEADLINE:.0f} s")
            wake = min(next_echo, next_ping if a.edge else next_echo, stop)
            try:
                s.pump(max(wake, now()))
            except TimeoutError:
                pass
            for body, code in s.messages():
                t = now()
                if body == 4 and code == UNAUTHENTICATED and outstanding:
                    emit(out, {"kind": "echo", "path": path_name(a), "rate": a.rate, "session": number,
                               "ms": ms(t - outstanding.pop(0))})
                    echoes += 1
                    if last_reply is not None:
                        worst_gap = max(worst_gap, t - last_reply)
                    last_reply = t
                else:
                    raise Failed("reply", f"field {body} code {code}")
            for at, payload in s.pongs:
                if payload in pings:
                    emit(out, {"kind": "wsping", "path": path_name(a), "rate": a.rate, "ms": ms(at - pings.pop(payload))})
            s.pongs = []
    except Failed as e:
        reason = str(e)
    except (OSError, TimeoutError) as e:
        reason = f"io: {type(e).__name__}"
    finally:
        s.carrier.close()
    emit(out, {"kind": "end", "path": path_name(a), "rate": a.rate, "session": number,
               "echoes": echoes, "worst_gap_ms": ms(worst_gap), "reason": reason})
    return reason == "session end"


def connect_loop(a, out, count, end, body):
    ident = identity(a)
    emit(out, {"kind": "identity", "path": path_name(a), "game": ident["game"], "protocol": ident["protocol"],
               "content": ident["content"][:12]})
    failures, number, last_connect = 0, 0, None
    every = max(a.every, MIN_CONNECT_SPACING)
    while number < count and now() < end:
        if last_connect is not None:
            time.sleep(max(0.0, last_connect + every - now()))
        last_connect = now()
        number += 1
        try:
            body(ident, number)
            failures = 0
        except Failed as e:
            failures += 1
            emit(out, {"kind": "error", "path": path_name(a), "session": number, "phase": e.phase, "detail": e.detail})
        except (OSError, TimeoutError) as e:
            failures += 1
            emit(out, {"kind": "error", "path": path_name(a), "session": number, "phase": "io", "detail": type(e).__name__})
        if failures >= 3:
            emit(out, {"kind": "stopped", "reason": "three failed connects in a row"})
            return 1
    return 0


def run(a):
    end = now() + a.minutes * 60
    with open(a.out, "a") as out:
        return connect_loop(a, out, 10**6, end, lambda ident, n: session(a, ident, out, n, end))


def connects(a):
    with open(a.out, "a") as out:
        def one(ident, n):
            s = Session(a, ident)
            s.carrier.close()
            emit(out, {"kind": "connect", "path": path_name(a), "session": n, **s.timings})
        return connect_loop(a, out, a.count, now() + 3600, one)


def percentile(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, int(-(-p * len(xs) // 100)) - 1))]


def stats(xs):
    return {"n": len(xs), "median": percentile(xs, 50), "p95": percentile(xs, 95),
            "p99": percentile(xs, 99), "max": max(xs)} if xs else {"n": 0}


def summary(a):
    records = []
    for name in a.files:
        with open(name) as f:
            records += [json.loads(line) for line in f if line.strip()]
    groups = {}
    for r in records:
        if r["kind"] in ("echo", "wsping"):
            groups.setdefault((r["kind"], r["path"], r["rate"]), []).append(r["ms"])
        elif r["kind"] == "connect":
            for k, v in r.items():
                if k.endswith("_ms"):
                    groups.setdefault(("connect " + k[:-3], r["path"], ""), []).append(v)
    gaps = {}
    for r in records:
        if r["kind"] == "end":
            gaps.setdefault((r["path"], r["rate"]), []).append(r["worst_gap_ms"])
    result = {f"{k} {p} {rate}".strip(): stats(v) for (k, p, rate), v in sorted(groups.items(), key=str)}
    for (p, rate), v in sorted(gaps.items(), key=str):
        result[f"worst gap {p} {rate}"] = {"n": len(v), "max": max(v)}
    for spec in a.icmp:
        name, _, path = spec.partition("=")
        with open(path) as f:
            text = f.read()
        times = [float(x) for x in re.findall(r"time=([0-9.]+)", text)]
        result[f"icmp {name}"] = stats(times)
        result[f"icmp {name} lost"] = {"n": text.count("no answer")}
    errors = [r for r in records if r["kind"] in ("error", "stopped")]
    result["errors"] = {"n": len(errors), "reasons": sorted({f"{r.get('phase', 'run')}: {r.get('detail', r.get('reason', ''))}" for r in errors})}
    ends = [r["reason"] for r in records if r["kind"] == "end" and r["reason"] != "session end"]
    result["sessions ended early"] = {"n": len(ends), "reasons": sorted(set(ends))}
    if a.json:
        print(json.dumps(result, indent=1))
        return 0
    for name, s in result.items():
        if "median" in s:
            print(f"{name:32} n={s['n']:6}  median {s['median']:8.2f}  p95 {s['p95']:8.2f}  p99 {s['p99']:8.2f}  max {s['max']:8.2f} ms")
        elif "max" in s:
            print(f"{name:32} sessions={s['n']:3}  worst {s['max']:8.2f} ms")
        else:
            print(f"{name:32} {s}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="verb", required=True)
    for verb in ("run", "connects"):
        q = sub.add_parser(verb)
        where = q.add_mutually_exclusive_group(required=True)
        where.add_argument("--edge", help="the realm's wss:// edge (spec 12)")
        where.add_argument("--direct", help="HOST:PORT of the game port")
        q.add_argument("--host", required=True, help="the realm certificate's name (realm.host)")
        q.add_argument("--ca", help="a CA for a dev realm; the system's roots otherwise")
        q.add_argument("--manifest")
        q.add_argument("--package")
        q.add_argument("--game")
        q.add_argument("--content")
        q.add_argument("--protocol", type=int)
        q.add_argument("--every", type=float, default=10.0, help="seconds between connects (at least 7)")
        q.add_argument("--out", required=True)
        if verb == "run":
            q.add_argument("--rate", type=float, default=1.0, help="echoes a second, 0.2 to 20")
            q.add_argument("--minutes", type=float, default=10.0, help="at most 60")
            q.add_argument("--session-secs", type=float, default=120.0, help="at most 600")
        else:
            q.add_argument("--count", type=int, default=30, help="at most 100")
    s = sub.add_parser("summary")
    s.add_argument("files", nargs="*")
    s.add_argument("--icmp", action="append", default=[], metavar="NAME=FILE",
                   help="`ping -D -O -i 1` output to summarize beside the records")
    s.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    if a.verb == "summary":
        return summary(a)
    if a.verb == "run" and not (0.2 <= a.rate <= 20 and 0 < a.minutes <= 60 and 5 <= a.session_secs <= 600):
        p.error("--rate 0.2..20, --minutes up to 60, --session-secs 5..600")
    if a.verb == "connects" and not 1 <= a.count <= 100:
        p.error("--count 1..100")
    pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    return run(a) if a.verb == "run" else connects(a)


if __name__ == "__main__":
    sys.exit(main())
