# The realm's host

Spec 07 asks for this record. The host is the maintainer's machine, not a VPS (Q64).

| | |
|---|---|
| Host | `gn100-69be` (`gn100-69be.local`), the maintainer's NVIDIA GB10 box |
| Hardware | aarch64, 20 cores, 121 GiB (shared with other work), 1.9 TB NVMe |
| OS | Ubuntu 24.04 LTS |
| Network | Home connection (Google Fiber); LAN `192.168.86.52` (wired) |
| Checkout | `~/Projects/N3E-Realm` (`git pull` from `origin`) |
| Stack | `deploy/compose.prod.yaml` via `tools/host-realm`, with the `edge` profile |
| Realm | `test-openko-<package hash[:12]>` (Q63) |
| Public reach | `wss://play.openko.net/v1/wire` through Cloudflare and the realm's tunnel (spec 12); releases at `https://releases.openko.net`. No forwarded ports; the game port is on loopback only. |
| DNS | openko.net on Cloudflare (moved from GoDaddy 2026-11-01); `play` and `releases` are the tunnel's proxied routes |
| TLS | Let's Encrypt for `play.openko.net`, DNS-01, `tools/host-tls`; first issued 2026-11-01, expires 2027-01-30, renewed daily from the maintainer's crontab |

## Deviations from spec 07

- **No provider scrubbing.** The volumetric layer is Cloudflare's network in front of
  the WebSocket edge (spec 12); the host's address is in no DNS record.
- **No `deploy`/`ops` users, no `/opt` or `/etc/n3e-realm` layout:** the stack runs from
  the maintainer's checkout as their user, with `.env` (mode 0600) in the checkout.
  Revisit when CD deploys here (M5).
- **Content and TLS are host paths** (`N3E_PACKAGE_PATH`, `N3E_TLS_PATH`) until CD's
  content image exists. The package is cooked on the workstation, which has the KO tree,
  and copied: `make realm-assets && rsync -a --delete build/packages/moradon/
  gn100-69be.local:Projects/N3E-Realm/build/packages/moradon/`.
- **TLS files** are `/etc/n3e-realm/tls/server.pem` and `server.key` (owned by uid
  1000), copied there by `tools/host-tls` from `/etc/letsencrypt`; the DNS token is
  `/etc/n3e-realm/cloudflare.ini` (root, 0600). Certbot runs from its image through
  Docker, so nothing needs sudo after the token file. The renewal line, added by the
  maintainer (installing it is theirs):
  `17 4 * * * cd ~/Projects/N3E-Realm && tools/host-tls renew >> ~/.cache/n3e-host-tls.log 2>&1`
- **Backups:** none yet. Planned: nightly `pg_dump` to the workstation.

## Releases

Built on the workstation (the KO tree and the GPU are there) and copied:

```sh
make realm-assets
python tools/local_release.py --hosted https://releases.openko.net --host play.openko.net \
  --edge wss://play.openko.net/v1/wire --realm-id openko --realm-name OpenKO \
  [--client windows-x86_64=<CI's client-windows-x86_64 archive>]
rsync -a --delete build/packages/moradon/ gn100-69be.local:Projects/N3E-Realm/build/packages/moradon/
rsync -a --delete build/hosted-release/ gn100-69be.local:Projects/N3E-Realm/build/hosted-release/
ssh gn100-69be.local 'cd ~/Projects/N3E-Realm && git pull --ff-only && tools/host-realm'
```

Players: `realm-launcher --add-realm openko https://releases.openko.net/manifest.json`,
then `realm-launcher --realm openko` (no `--ca`: both certificates are public).

## `.env` variables

Names only: `DISCORD_BOT_TOKEN`, `DISCORD_GUILD_ID`, `DISCORD_CHANNEL_ANNOUNCE`,
`DISCORD_CHANNEL_OPS`, `DISCORD_ROLE_MOD`, `DISCORD_ROLE_OPS`, `DISCORD_CLIENT_ID`,
`DISCORD_CLIENT_SECRET`, `N3E_DB_PASSWORD` (generated on the host), `N3E_REALM_PREFIX`,
`N3E_TLS_PATH` (`/etc/n3e-realm/tls`), `REALM_ADMIN_TOKEN` (minted on the host by
`tools/host-realm mint-bot`; the workstation's token belongs to another database),
`CLOUDFLARE_TUNNEL_TOKEN` (the realm's own tunnel, not foilstack's), `N3E_BIND`
(`127.0.0.1`), `N3E_TRUSTED_PROXY_CIDRS` (`172.31.77.11/32`, the edge).

Tunnel routes (Cloudflare Zero Trust, the realm's tunnel): `play.openko.net` →
`http://edge:8443`, `releases.openko.net` → `http://releases:80`.

Only one bot may run per Discord token: the workstation's `tools/local-realm` stack
must not start its bot while this one runs.
