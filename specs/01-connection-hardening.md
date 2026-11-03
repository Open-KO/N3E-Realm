# 01 — Connection hardening

Layer 2 of the DDoS design in `architecture.md` ("Connection-level, in the server").
Everything here happens **before** any TLS work, at accept time, and is cheap by design.
Layer 1 (volumetric) is the VPS provider's and is covered in spec 07.

## Purpose

Make an unauthenticated connection cost the server as close to nothing as possible,
bound how many of them one source can hold, and give the deploy pipeline a switch to
stop admitting new ones.

## Scope

In: the accept loop for `:7777`; per-IP and global limits; pre-handshake idle timeout;
the time bounds on a connection's frames after its `Handshake`; drain state; counters.
Out: the rest of what happens after the game-wire `Handshake` is accepted (the server's
existing per-frame and per-tick limits cover that); IP reputation lists; geo-blocking.

## Where it lives

In the game server's accept loop (`server/src/network.rs` after migration, spec 09).
Today that loop admits up to 64 TLS sockets behind a semaphore with a 2 s handshake
deadline. The checks below go **in front of** the semaphore, before TLS starts.

## Interfaces

### Configuration

| Env var | Default | Meaning |
|---|---|---|
| `N3E_LISTEN` | `0.0.0.0:7777` | Public listener (existing). |
| `N3E_MAX_CONNECTIONS` | `64` | Global cap on sockets past accept (replaces the hardcoded 64). |
| `N3E_IP_MAX_CONCURRENT` | `3` | Open sockets per source IP (any state). |
| `N3E_IP_CONNECT_RATE` | `10` | New connections per source IP per 60 s window. |
| `N3E_PREAUTH_IDLE_MS` | `2000` | Accept → first complete `Handshake` frame, else close. Matches the existing handshake deadline. |
| `N3E_CONNECTION_IDLE_MS` | `30000` | After the `Handshake`: the longest wait for the next frame to begin, else close. See "After the handshake". |
| `N3E_PREAUTH_MAX_SLOTS` | `16` | Sockets between accept and completed login at once. Bounds TLS handshakes in flight. |
| `N3E_TRUSTED_PROXY_CIDRS` | *(empty)* | If set, PROXY protocol v2 is accepted from these ranges and the client IP is taken from it (future relay tier). Otherwise PROXY headers are rejected. Comma-separated `a.b.c.d/n` or `x::/n`; a bare address is one host. An IPv4-mapped range (`::ffff:a.b.c.d/n`) means the IPv4 range `/n-96`, and one shorter than `/96`, or any entry that does not parse, refuses to start, naming the variable. |

"Source IP" is the TCP peer address, or the PROXY-protocol original address when the
peer is a trusted proxy. IPv6 sources are bucketed by /64. Every numeric limit must be a
whole number from 1; anything else refuses to start, naming the variable.

### Status counters

Exposed via `GET /v1/realm/status` (spec 03) under `"connections"`:

```json
{
  "open": 41, "preauth": 2, "authenticated": 39,
  "refused_ip_concurrent": 1203, "refused_ip_rate": 88,
  "refused_global": 0, "refused_preauth_slots": 12,
  "refused_draining": 3, "refused_proxy": 0, "preauth_timeouts": 540
}
```

Process-lifetime monotonic counters, atomics, no locks on the hot path.

## Behaviour

Order of checks on every accepted TCP socket, **before** reading a byte and before
starting TLS:

1. **Draining?** If drain is set (spec 03) → close, `refused_draining++`.
2. **Global cap.** `open >= N3E_MAX_CONNECTIONS` → close, `refused_global++`.
3. **Per-IP concurrent.** Open sockets from this source `>= N3E_IP_MAX_CONCURRENT` →
   close, `refused_ip_concurrent++`.
4. **Per-IP rate.** Connects from this source in the last 60 s `>= N3E_IP_CONNECT_RATE`
   → close, `refused_ip_rate++`. The attempt still counts.
5. **Pre-auth slots.** `preauth >= N3E_PREAUTH_MAX_SLOTS` → close,
   `refused_preauth_slots++`.
6. Otherwise take a pre-auth slot, start the idle timer, begin TLS.

"Close" means `close()` with no bytes written. No TLS alert, no game-wire `Error`: that
costs cycles and tells the attacker which rule they tripped. The close is a reset
(`SO_LINGER` 0): still no payload, and no `TIME_WAIT` entry left on the server for each
socket of a flood.

A **trusted proxy**'s socket passes steps 1–2 at accept; steps 3–5 run once its PROXY v2
header (read under the idle timer, at most 232 bytes) names the client. A trusted peer
may also connect directly. From any other peer, a first byte that starts a PROXY v2
signature (TLS starts with `0x16`) is a PROXY header: close, `refused_proxy++`.

After step 6:

- The idle timer covers the TLS handshake **and** the first game-wire frame, and is the
  only bound on them. No complete first frame within `N3E_PREAUTH_IDLE_MS` → close,
  `preauth_timeouts++`.
- The pre-auth slot is released when login completes (spec 02) or the socket closes.
- Per-IP state is in-memory only: an LRU keyed by source IP, cap 65,536 entries. Not in
  Redis — one realm process, and a Redis round trip at accept time defeats the purpose.
- The rate window is a fixed 60 s ring or an equivalent sliding approximation; ±10 %
  precision is fine.

### After the handshake

From the `Handshake` reply until the socket closes, through login, the realm and
character screens and the world alike, each frame is bounded twice:

- **Between frames:** the next frame's first byte within `N3E_CONNECTION_IDLE_MS` of the
  server asking for it, else close. The client pings every second in every phase
  (`client/network/world.cpp`), so only an outage this long ends a session; it is under
  the edge's 75 s idle close (spec 12), so the server, not the edge, names it.
- **Within a frame:** once its first byte has arrived, the rest of it (the length
  prefix and the body) within 2 s, else close; each frame the server writes, within 2 s.

RQ-131: one 2 s bound used to cover both, so any 2 s gap in the client's stream (a
Wi-Fi or tunnel hiccup) ended the session; the 30 s default is Q88's. A socket in this phase before login still
holds its pre-auth slot; `N3E_IP_MAX_CONCURRENT` bounds how many one source holds.

Either close writes the server's one line for a session it ended (PQ-427), naming the
gap or the stall: `session from <address> closed by the server: no frame begun for
30 s, the connection idle limit`, or `…: a frame begun but not completed within 2 s
(6 of its 14 bytes)` (bytes read of the frame, its 4 length bytes included), or
`…: a frame not written within 2 s`.

### Drain

A single boolean in process memory, set/cleared via spec 03. While set: new sockets
are refused at step 1; existing sessions continue; `status.draining == true`. The
process does not exit on its own — CD restarts it.

### Logging

One line per minute at most, counting each refusal class since the last line, and none
in a minute with no refusals:
`connections refused ip_concurrent=1203 ip_rate=88 global=0 preauth_slots=12 draining=3 proxy=0 preauth_timeouts=540`.
Per-connection refusal logging is forbidden (it turns a SYN flood into a disk flood).

## Failure modes

| Situation | Behaviour |
|---|---|
| LRU full | Evict least-recently-seen. A flood from many IPs degrades to the global cap only — the intended fallback. |
| Clock jumps | Monotonic clock for the window. |
| PROXY header from an untrusted peer | Close, `refused_proxy++`. |
| Players behind CGNAT share an IP | They hit `N3E_IP_MAX_CONCURRENT`. Accepted trade; raise in `.env`. Document for mods. |
| Clients reach the server through Docker's loopback publish (the local stack) | All arrive from the Compose gateway address: the local `compose.yaml` defaults the per-source limits to 64 concurrent and 600/min (Q31). Production traffic arrives by DNAT with its own source address. |

## Acceptance tests

Scriptable against a running stack with a throwaway cert:

1. **Per-IP concurrent.** Open `cap + 5` idle TCP connections from one address. Exactly
   `cap` complete TLS; the rest close with zero bytes received, each within 10 ms.
   `refused_ip_concurrent += 5`.
2. **Per-IP rate.** Connect-and-close `rate + 5` times in one second. Exactly `rate`
   admitted; `refused_ip_rate += 5`. After 60 s the source is admitted again.
3. **Idle timeout.** TCP connect, send nothing → closed within `idle + 100 ms`. Complete
   TLS, send nothing → same.
4. **Pre-auth slots.** Hold `slots` connections mid-TLS; the next is refused without a
   ServerHello.
5. **Drain.** Set drain via spec 03. An authenticated client keeps playing ≥ 30 s; a new
   connection is refused immediately; `status.draining == true`. Resume → admitted.
6. **No per-connection logs.** Test 1 in a loop for 10 s → log grows ≤ one line per
   class per minute.
7. **Cost.** Test 1 continuously from 4 addresses, 500 connects/s each → server CPU
   < 5 % of one core above idle for the release binary (measure; record the figure).
   Recorded 2026-10-30, 8-thread desktop, loopback: release 4.2–4.7 % (user 1.1–1.3 %,
   system 3.1–3.4 %; 19–22 µs per connect, kernel accept/close most of it); the debug
   build `make live` runs spends 7–8 % and is held to 15 %. Unpaced (6,300 connects/s):
   release 10 %.
8. **Existing suites still pass.** `tests/multiplayer.py` and the `live` suites are
   unaffected with the realm's global and pre-auth defaults. Every suite connects from one
   address, so the harness lifts the per-source limits (Q31); `connections_live` tests
   them with small values from distinct loopback sources.
9. **Frames after the handshake.** A 5 s gap between frames keeps the session; a frame
   whose length prefix has arrived but whose body stalls closes within 2 s + 0.3 s; a
   session that sends nothing closes at `N3E_CONNECTION_IDLE_MS` (± 0.3 s); each close
   logs its line.

Evidence: `tests/connections_live.py` (tests 1–7 and 9, the roadmap's 500 connections from
one address, PROXY v2 trusted and untrusted, the status counters); test 9's bounds also
in `server/src/network.rs` (`a_gap_between_frames_up_to_the_idle_limit_is_survived`,
`a_stalled_frame_still_closes_in_two_seconds`).

## Open questions

None.
