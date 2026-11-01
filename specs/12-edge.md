# 12 — The WebSocket edge: the game wire through Cloudflare

**Status: done 2026-11-01; tests 1–6 pass.** Milestone M7a
in [`00-roadmap.md`](00-roadmap.md). Why: [`architecture.md`](../docs/architecture.md),
"DDoS", and Q64.

## Purpose

Let a realm run on a host whose address must stay private (the maintainer's own
machine on a home connection, Q64) and still take a public flood on someone else's
network. The game wire travels as a WebSocket through Cloudflare's free proxy and a
Cloudflare Tunnel; the host opens no inbound port and its address is never published.

Cloudflare proxies raw TCP only with Spectrum (Enterprise), but it proxies WebSockets on
every plan, and we ship the client, so the client can speak WebSocket.

## Scope

In: an optional `edge` URL in the realm profile; the client's WebSocket transport; a
bridge service on the host between `cloudflared` and the game port; source addresses
through the bridge; the host's tunnel. Out: changes to the game wire itself, UDP,
Cloudflare features beyond DNS, the proxy and Tunnel, any paid Cloudflare product.

## Shape

```
client ──TLS(Cloudflare cert)──▶ Cloudflare edge ──Tunnel──▶ cloudflared ──ws──▶ realm-edge ──TCP+PROXY v2──▶ server :7777
   └──────────── inner TLS (the realm's own certificate), the unchanged game wire ────────────────────────────────▶
```

- **Outer:** an ordinary `wss://` connection to Cloudflare, verified against the system
  roots. Cloudflare sees the HTTP upgrade and opaque binary frames.
- **Inner:** the game wire's existing TLS session with the server, carried in WebSocket
  binary frames. The client verifies the realm certificate for `realm.host` exactly as
  today. Cloudflare never sees session tokens or game traffic.
- **Bridge (`realm-edge`):** accepts WebSocket upgrades from `cloudflared` only, opens a
  TCP connection to the server, writes a PROXY protocol v2 header naming the player's
  address (from `CF-Connecting-IP`), then copies bytes both ways. It does no TLS and
  parses nothing past the upgrade.
- **Server:** unchanged. Spec 01's per-source limits apply to the address in the PROXY
  header, because `N3E_TRUSTED_PROXY_CIDRS` names the bridge.

## Interfaces

### Realm profile

The manifest's `realm` object (spec 04) and the client's `realm.json` gain one optional
field:

```json
"realm": { "id": "openko", "name": "OpenKO", "host": "play.openko.net", "port": 7777,
           "edge": "wss://play.openko.net/v1/wire", "discord_client_id": "…" }
```

- `edge` absent: the client connects to `host:port` over TCP as today.
- `edge` present: the client opens the WebSocket at that URL (`wss` only; anything else
  refuses to start) and runs the inner TLS with SNI and verification for `host`. `port`
  is ignored for the connection.
- The launcher copies `edge` into `realm.json` like the other fields; the realm id rule
  (spec 04, a changed `realm.id` is refused) is unchanged.

### WebSocket

- Path `/v1/wire`, subprotocol `n3e-wire.1` (`Sec-WebSocket-Protocol`); the bridge
  refuses an upgrade without it (`400`).
- Binary frames only. Each frame carries any number of bytes of the inner TLS stream;
  receivers reassemble. A frame over 64 KiB + 1 KiB closes the connection with status
  1009. Text frames close it with 1003. Ping and pong are answered; `realm-edge` pings
  every 30 s and closes after 75 s without a frame (Cloudflare drops idle sockets at
  100 s).
- The client's outer handshake has the inner handshake's deadline (spec 01,
  `N3E_PREAUTH_IDLE_MS`) plus 5 s.
- A closed WebSocket is a closed connection: the client reconnects as it does after a
  dropped TCP connection (spec 02, the session token).

### `realm-edge`

A Rust binary in this workspace (`edge/`), image `deploy/Dockerfile --target edge`.

| Env var | Default | Meaning |
|---|---|---|
| `REALM_EDGE_LISTEN` | `0.0.0.0:8443` | Plain HTTP listener for `cloudflared`, on the compose network only, never published. |
| `REALM_EDGE_UPSTREAM` | `server:7777` | The game port. |
| `REALM_EDGE_MAX_CONNECTIONS` | `256` | Open WebSockets; past it, upgrades get `503`. |
| `REALM_EDGE_TRUSTED_CIDRS` | *(required)* | Peers allowed to connect (the `cloudflared` container's network); others are closed before reading. |

- The player's address is `CF-Connecting-IP`; an upgrade without it, or with a value
  that is not one address, is refused (`400`). It is trusted only because the peer is
  `cloudflared` (`REALM_EDGE_TRUSTED_CIDRS`).
- Upgrade requests are bounded: 8 KiB of headers, 5 s to complete.
- One line per connection at close, on stderr: `edge close src=<address> bytes_in=
  bytes_out= secs= reason=`. `src` is the `CF-Connecting-IP` address once known, else
  the peer; the byte counts are the inner stream's (frame payloads). No headers are
  logged. Refusals before the upgrade log the same line with their reason
  (`untrusted`, `timeout` 408, `oversize` 431, `malformed`, `path` 404, `method` 405,
  `upgrade` and `protocol` 400, `no_source` 400, `full` 503, `upstream` 502).
- The upstream connection and its PROXY header are made before the `101`: a server
  that cannot be reached is a `502`, not an upgraded socket that closes.
- An idle client (no frame for 75 s, or one that stops reading for 75 s) is closed
  with 1001.
- Health: `GET /live` on the same listener (`200`), which loopback may always ask;
  `realm-edge health` asks it, for compose (the image has no curl).

### Host

- `cloudflared` runs in the realm's compose stack (`deploy/compose.prod.yaml`, `edge`
  profile) with the realm's own tunnel token, `CLOUDFLARE_TUNNEL_TOKEN` in `.env`. The
  tunnel's public hostname `play.openko.net` routes to `http://edge:8443`.
- The server sets `N3E_TRUSTED_PROXY_CIDRS` to the bridge's address and publishes no
  public port: `N3E_BIND=127.0.0.1` keeps `:7777` on loopback for the host's own tests.
- `play.openko.net` is a proxied (orange) record created by the tunnel. No DNS record
  holds the host's address. Cloudflare's settings: WebSockets on (the default), no
  caching rules for the path.
- The realm certificate for the inner TLS is Let's Encrypt for `play.openko.net`,
  issued by certbot DNS-01 with a Cloudflare API token limited to the openko.net zone's
  DNS (`CLOUDFLARE_DNS_API_TOKEN`, read from a root-only file, never `.env`). The renew
  hook copies the pair to `N3E_TLS_PATH` and restarts the server (spec 07, "TLS").
- Launcher releases and the manifest are served by the same tunnel at
  `releases.openko.net` until CD publishes GitHub Releases (spec 06); then that route
  goes away.

## Failure modes

| Failure | Behaviour |
|---|---|
| Cloudflare or the tunnel is down | The client's connect fails with the existing "cannot reach the realm" path; nothing reaches the host. |
| Cloudflare restarts an edge and drops sockets | Players reconnect with their session token (spec 02). |
| The bridge is down | `cloudflared` returns 502; the client reports the connect failure. |
| The server is down or draining | The upstream connect fails: `502` before the upgrade. A server that closes an upgraded socket (a refusal, a drain): close 1000; an upstream error after the upgrade: 1011. |
| `CF-Connecting-IP` missing | `400`; counted in the close log as `reason=no_source`. |
| A flood | Cloudflare's network takes it; the host sees only what the tunnel delivers, bounded by `REALM_EDGE_MAX_CONNECTIONS` and spec 01. |

## Security

- The host's address appears in no DNS record, manifest, log line sent to Discord, or
  document. Nothing listens on a public interface.
- `CF-Connecting-IP` is trusted only from `cloudflared`; the server trusts PROXY headers
  only from the bridge.
- The inner TLS is unchanged, so Cloudflare cannot read or alter the game wire; at
  worst it can drop it.
- The tunnel token and the DNS API token are secrets (spec 07, R2 rotation applies).
  The DNS token can edit openko.net's records and nothing else.

## Acceptance tests

1. A client with `edge` connects through a loopback stand-in for the edge (a WebSocket
   terminator in the test) to `realm-edge` and the server, logs in, moves, and the
   server's status shows the stand-in's `CF-Connecting-IP` as the source.
2. Spec 01's per-IP cap applies to the forwarded address: four sockets with the same
   `CF-Connecting-IP` admit three; a fourth with another address is admitted.
3. `realm-edge` refuses a peer outside `REALM_EDGE_TRUSTED_CIDRS`, an upgrade without
   the subprotocol or `CF-Connecting-IP`, text frames and oversize frames, as specified.
4. After the edge closes its WebSockets (an edge restart), the client's next
   connection through the edge logs in with its stored session token, with no Discord
   prompt. (The client does not reconnect on its own after a drop; the player's next
   login or a restart does, as after a dropped TCP connection.)
5. A `realm.json` without `edge` connects over TCP exactly as before (existing suites).
6. Manual, on the host: a client outside the home network (a phone hotspot) connects
   to `wss://play.openko.net/v1/wire` and plays; `play.openko.net` resolves only to
   Cloudflare addresses; the router has no forwarded ports.

## Open questions

Q64 (why), Q65 (Cloudflare's free-plan WebSocket limits are unpublished).

Evidence (2026-11-01, this workstation): `tests/edge_live.py --graphical` (tests 1–4
and the non-`wss` refusal), `cargo test -p realm-edge` (framing, PROXY v2 bytes,
refusals), the existing suites for test 5; test 6 by the maintainer on Linux and
Windows from outside the home network.
