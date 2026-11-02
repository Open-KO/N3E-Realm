# The realm's host

Spec 07 asks for this record. The host is the maintainer's machine, not a VPS (Q64).

| | |
|---|---|
| Host | the maintainer's home machine on their LAN (its name is in `deploy/host.local`, below) |
| Hardware | aarch64 (shared with other work) |
| OS | Ubuntu 24.04 LTS |
| Network | Home connection, wired to the LAN |
| Checkout | a clone of this repository in the maintainer's home directory (`git pull` from `origin`) |
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
  and copied as in "Releases" below.
- **TLS files** are `/etc/n3e-realm/tls/server.pem` and `server.key` (owned by uid
  1000), copied there by `tools/host-tls` from `/etc/letsencrypt`; the DNS token is
  `/etc/n3e-realm/cloudflare.ini` (root, 0600). Certbot runs from its image through
  Docker, so nothing needs sudo after the token file. The renewal line, added by the
  maintainer (installing it is theirs):
  `17 4 * * * cd <checkout> && tools/host-tls renew >> ~/.cache/n3e-host-tls.log 2>&1`
- **Backups:** none yet. Planned: nightly `pg_dump` to the workstation.

## Releases

Built on the workstation (the KO tree and the GPU are there) and copied. Where the host
is comes from the environment or from the git-ignored `deploy/host.local`, a shell
fragment the commands below source:

```sh
# deploy/host.local (git-ignored; never commit the values)
N3E_REALM_HOST=realm-host.example     # the host as ssh and rsync reach it (a user goes in ~/.ssh/config)
N3E_REALM_HOST_DIR=src/N3E-Realm      # the host's checkout, relative to its home directory
```

```sh
test -f deploy/host.local && . deploy/host.local
: "${N3E_REALM_HOST:?set it in deploy/host.local}" "${N3E_REALM_HOST_DIR:?set it in deploy/host.local}"
make realm-assets
python tools/local_release.py --hosted https://releases.openko.net --host play.openko.net \
  --edge wss://play.openko.net/v1/wire --realm-id openko --realm-name OpenKO \
  [--client windows-x86_64=<CI's client-windows-x86_64 archive>]
cp <CI's realm-launcher.exe> build/hosted-release/realm-launcher.exe   # until M5 publishes launchers
cp target/release/realm-launcher build/hosted-release/realm-launcher-linux-x86_64
rsync -a --delete build/packages/moradon/ "$N3E_REALM_HOST:$N3E_REALM_HOST_DIR/build/packages/moradon/"
rsync -a --delete build/hosted-release/ "$N3E_REALM_HOST:$N3E_REALM_HOST_DIR/build/hosted-release/"
ssh "$N3E_REALM_HOST" "cd '$N3E_REALM_HOST_DIR' && git pull --ff-only && tools/host-realm"
```

Players download `https://releases.openko.net/realm-launcher.exe` (Windows) or
`realm-launcher-linux-x86_64` and run it: OpenKO is the launcher's compiled-in default
profile (`launcher/src/profiles.rs`), so no arguments are needed and no `--ca` (both
certificates are public).

## `.env` variables

Names only: `DISCORD_BOT_TOKEN`, `DISCORD_GUILD_ID`, `DISCORD_CHANNEL_ANNOUNCE`,
`DISCORD_CHANNEL_OPS`, `DISCORD_ROLE_MOD`, `DISCORD_ROLE_OPS`, `DISCORD_CLIENT_ID`,
`DISCORD_CLIENT_SECRET`, `N3E_DB_PASSWORD` (generated on the host), `N3E_REALM_PREFIX`,
`N3E_TLS_PATH` (`/etc/n3e-realm/tls`), `REALM_ADMIN_TOKEN` (minted on the host by
`tools/host-realm mint-bot`; the workstation's token belongs to another database),
`CLOUDFLARE_TUNNEL_TOKEN` (the realm's own tunnel, not one another service on the host uses), `N3E_BIND`
(`127.0.0.1`), `N3E_TRUSTED_PROXY_CIDRS` (`172.31.77.11/32`, the edge).

Tunnel routes (Cloudflare Zero Trust, the realm's tunnel): `play.openko.net` →
`http://edge:8443`, `releases.openko.net` → `http://releases:80`.

Only one bot may run per Discord token: the workstation's `tools/local-realm` stack
must not start its bot while this one runs.
