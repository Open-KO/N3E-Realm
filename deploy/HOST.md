# The realm's host

Spec 07 asks for this record. The host is the maintainer's machine, not a VPS (Q64).

| | |
|---|---|
| Host | `gn100-69be` (`gn100-69be.local`), the maintainer's NVIDIA GB10 box |
| Hardware | aarch64, 20 cores, 121 GiB (shared with other work), 1.9 TB NVMe |
| OS | Ubuntu 24.04 LTS |
| Network | Home connection (Google Fiber); LAN `192.168.86.52` (wired) |
| Checkout | `~/Projects/N3E-Realm` (`git pull` from `origin`) |
| Stack | `deploy/compose.prod.yaml` via `tools/host-realm` |
| Realm | `test-openko-<package hash[:12]>` (Q63) |
| Public reach | None yet: LAN only until spec 12 (M7a). No forwarded ports. |

## Deviations from spec 07

- **No provider scrubbing.** The volumetric layer is to be Cloudflare's network in front
  of the WebSocket edge (spec 12); until then nothing is public.
- **No `deploy`/`ops` users, no `/opt` or `/etc/n3e-realm` layout:** the stack runs from
  the maintainer's checkout as their user, with `.env` (mode 0600) in the checkout.
  Revisit when CD deploys here (M5).
- **Content and TLS are host paths** (`N3E_PACKAGE_PATH`, `N3E_TLS_PATH`) until CD's
  content image exists. The package is cooked on the workstation, which has the KO tree,
  and copied: `make realm-assets && rsync -a --delete build/packages/moradon/
  gn100-69be.local:Projects/N3E-Realm/build/packages/moradon/`.
- **TLS is the local CA** (`deploy/local-ca.sh`, names `192.168.86.52` and
  `gn100-69be.local`, 30 days, renewed by the script) until Let's Encrypt via DNS-01
  (spec 12, "Host"). LAN clients pass its `ca.pem` with `--ca`.
- **Backups:** none yet. Planned: nightly `pg_dump` to the workstation.

## `.env` variables

Names only: `DISCORD_BOT_TOKEN`, `DISCORD_GUILD_ID`, `DISCORD_CHANNEL_ANNOUNCE`,
`DISCORD_CHANNEL_OPS`, `DISCORD_ROLE_MOD`, `DISCORD_ROLE_OPS`, `DISCORD_CLIENT_ID`,
`DISCORD_CLIENT_SECRET`, `N3E_DB_PASSWORD` (generated on the host), `N3E_REALM_PREFIX`,
`N3E_TLS_PATH`, `REALM_ADMIN_TOKEN` (minted on the host by `tools/host-realm mint-bot`;
the workstation's token belongs to another database).

Only one bot may run per Discord token: the workstation's `tools/local-realm` stack
must not start its bot while this one runs.
