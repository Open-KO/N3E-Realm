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
drain state; counters. Out: anything after the game-wire `Handshake` is accepted (the
server's existing per-frame and per-tick limits cover that); IP reputation lists;
geo-blocking.

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
| `N3E_PREAUTH_MAX_SLOTS` | `16` | Sockets between accept and completed login at once. Bounds TLS handshakes in flight. |
| `N3E_TRUSTED_PROXY_CIDRS` | *(empty)* | If set, PROXY protocol v2 is accepted from these ranges and the client IP is taken from it (future relay tier). Otherwise PROXY headers are rejected. |

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

Evidence: `tests/connections_live.py` (tests 1–7, the roadmap's 500 connections from one
address, PROXY v2 trusted and untrusted, the status counters).

## Open questions

None.
