# 07 — Deployment: VPS, compose, TLS, secrets, backups, rollback, rebuild

Implements O1–O6, Pushback #13 and DDoS layer 1/4 from `architecture.md`. This spec is
half configuration, half runbook. The runbook sections are meant to be executed
verbatim and kept current.

## Purpose

One VPS runs the whole backend. Everything on it is reproducible from this repo plus
the secrets listed in O5.

## Scope

In: provider choice criteria, host setup, `compose.yaml`, TLS issuance and renewal,
secret layout, backups and restore, rollback, origin hiding, the rebuild runbook. Out:
multi-node, HA, CDN, monitoring beyond what the Bot already surfaces (see Q15).

## Provider and host

- **Requirement:** always-on L3/L4 DDoS scrubbing included for game/TCP traffic
  (OVH "Game" anti-DDoS, Hetzner's standard protection, or equivalent). Not Cloudflare
  (Spectrum is Enterprise-only — see `architecture.md` DDoS ladder).
- Size: 4 vCPU / 8 GiB / 80 GiB SSD is ample (n3e caps at 64 sockets; Postgres and
  Redis are tiny). Record the chosen SKU in `deploy/HOST.md`.
- OS: Debian 12 or Ubuntu 24.04 LTS, unattended security upgrades on.
- Users: `deploy` (ssh key from CD, `sudo` for `docker compose` and `cat
  /etc/n3e-realm/ops.token` only — a narrow sudoers file), `ops` (human, full sudo).
  Root ssh disabled. Password auth disabled.
- Firewall (nftables or ufw): inbound `22` (ops IP allow-list if practical), `7777`,
  `80`/`443` **only during** cert issuance if using
  standalone certbot (prefer DNS-01 so they never open). Everything else dropped.
  Docker must not punch holes: compose publishes only `127.0.0.1:…` for anything that
  isn't the game port.
- Time: `chrony`. Logs: journald with `SystemMaxUse=1G`; docker `json-file` with
  `max-size=50m`, `max-file=5`.

## Layout on the host

```
/opt/n3e-realm/
  compose.yaml            # from the repo, copied by CD on each deploy
  .env                    # runtime secrets (O5), mode 0640 root:deploy
  content/                # named-volume mount target for the cooked package (spec 06)
/etc/n3e-realm/
  ops.token               # mode 0400 root:root; read via sudo by remote.sh only
  tls/fullchain.pem, privkey.pem   # copied from certbot on renewal (hook below)
/var/backups/n3e-realm/   # pre-deploy dumps (local, pruned to 14 days)
```

### `.env` (runtime, O5)

```
IMAGE_TAG=<sha>                # written by remote.sh
N3E_DB_PASSWORD=…
DISCORD_BOT_TOKEN=…
DISCORD_CLIENT_ID=…
DISCORD_CLIENT_SECRET=…
DISCORD_GUILD_ID=… DISCORD_CHANNEL_ANNOUNCE=… DISCORD_CHANNEL_OPS=…
DISCORD_ROLE_MOD=… DISCORD_ROLE_OPS=…
REALM_ADMIN_TOKEN=…            # the `bot` token
GITHUB_DISPATCH_TOKEN=…        # fine-grained PAT, actions:write, 90-day expiry → renewal date in HOST.md
N3E_ADMIN_LISTEN=172.31.77.10:7780  # the server's static compose-network address; compose publishes it to 127.0.0.1 on the host
```

Not in `.env`: the ops token (file above), TLS keys (files above), VPS ssh key (GitHub
Secrets only).

## Compose

`deploy/compose.prod.yaml`. Services: `postgres`, `redis`, `migrate`, `content-init`,
`server`, `bot`. Start from the imported local `compose.yaml` and change only:

- `server` ports: `0.0.0.0:7777:7777` and `127.0.0.1:7780:7780` (admin API reachable
  from the host for CD's `curl` and from `bot` over the compose network). `8080` is not
  published.
- `N3E_CERT`/`N3E_KEY` mount `/etc/n3e-realm/tls/fullchain.pem` / `privkey.pem`
  read-only. The container runs as `1000:1000`; `privkey.pem` is `0640 root:n3e` with
  gid 1000 — or copy with the right owner in the renewal hook.
- `N3E_REALM=prod`. The compose network has a fixed subnet (`172.31.77.0/24`) and
  `server` the static `ipv4_address` `172.31.77.10`; `N3E_ADMIN_LISTEN=172.31.77.10:7780`
  (RFC 1918, which spec 03 requires — it refuses `0.0.0.0`; the publish rule restricts
  the host side to loopback). Q29.
- `content-init`: `ghcr.io/<org>/realm-content:<hash>` copies `/package` into the
  `content` named volume and exits; `server` depends on it
  `service_completed_successfully`.
- `bot`: no ports; `depends_on: redis, server`; `restart: unless-stopped`;
  `REALM_ADMIN_URL=http://server:7780`.
- `restart: unless-stopped` on everything long-running; `server` `stop_grace_period`
  raised from `5s` to `30s` so SIGTERM drain can save positions.
- Postgres/Redis images stay pinned by digest as in n3e.

Health: compose healthchecks as in n3e (`n3e-server health`).

## TLS (O1)

- Domain: `play.<domain>` → VPS. Use **hostnames everywhere** (Launcher manifest, Bot messages, docs); never the IP (DDoS layer 4).
- Issue with certbot **DNS-01** (provider API plugin) so no HTTP port is ever opened.
  Fall back to standalone HTTP-01 with a temporary firewall rule only if DNS-01 is
  impossible.
- Renewal hook `/etc/letsencrypt/renewal-hooks/deploy/n3e-realm.sh`:
  ```
  install -o root -g root -m 0644 "$RENEWED_LINEAGE/fullchain.pem" /etc/n3e-realm/tls/fullchain.pem
  install -o root -g 1000 -m 0640 "$RENEWED_LINEAGE/privkey.pem"   /etc/n3e-realm/tls/privkey.pem   # gid 1000 = container user
  # n3e reads the cert at start; a restart kicks players, so go through the same gate CD uses:
  cd /opt/n3e-realm && RESTART_SERVER=true FORCE=false REASON="TLS renewal" ./deploy/remote.sh --local
  ```
  `remote.sh --local` skips image pulls and runs only the gated restart. Certs renew
  ~30 days before expiry, so a skip (players online) is retried daily by certbot's
  timer until it lands. (Q16: hot cert reload would remove this restart entirely.)
- Client trusts the system CA store; `--ca` is dev-only.

## Backups (O4)

- Nightly `pg_dump` at 04:30 UTC (before the 05:xx cron deploys
  are likely), `zstd`, uploaded to an object store (`rclone` to S3/R2/B2) under
  `n3e-realm/<yyyy>/<mm>/<dd>.sql.zst`, 30 daily + 12 monthly retained. Credentials in
  `/root/.config/rclone/rclone.conf` (0600) — another secret for O5's list.
- Pre-deploy dumps (spec 06) stay local, 14 days.
- **Restore rehearsal** (do once, then quarterly): on a scratch VM, `docker compose up
  postgres`, `zstd -d | psql`, start `server`, log in with a test client. Record the
  date in `HOST.md`.
- Content needs no backup (it's in Releases by hash). Redis needs no backup (sessions
  and tokens are in Postgres; the stream and `deploy:pending` are disposable).

## Rollback (O6)

Application: `workflow_dispatch` on a `deploy-*` tag (spec 06).
Database: stop `server`, `psql < dump`, start; then roll the application to the tag
that matches the dump. There are no down-migrations; write that in the ops channel
pinned message.

## Origin hiding (DDoS layer 4)

- No IP in any public artifact; `dig` will find it anyway, so the real control is being
  able to **move**: keep DNS TTL at 300 s, keep a second VPS image/snapshot ready at the
  provider, and document the IP-change procedure (change DNS, re-issue cert via DNS-01,
  update nothing else — everything is by hostname).
- If attacks persist past the provider's scrubbing: step 2 of the ladder in
  `architecture.md` (relay VPS). `REALM_TRUSTED_PROXY_CIDRS` (spec 01) exists for that
  day.

## Runbooks

### R1 — Fresh host to serving (≈ 30 min; the "rebuild" of Pushback #13)

1. Provision VPS per "Provider and host". Point `play.<domain>` at it.
2. `apt install docker.io docker-compose-plugin certbot python3-certbot-dns-<provider> rclone zstd jq chrony`.
3. Create users, sudoers, firewall, journald/docker log limits.
4. `certbot certonly --dns-<provider> -d play.<domain>`; install the
   renewal hook; run it once by hand.
5. `mkdir -p /opt/n3e-realm /etc/n3e-realm /var/backups/n3e-realm`; write `.env` from the
   password manager; `chmod`/`chown` as above.
6. Copy `deploy/compose.prod.yaml` to `/opt/n3e-realm/compose.yaml` (CD does this on
   every deploy afterwards).
7. First deploy by hand: `IMAGE_TAG=<latest deploy tag's sha> … ./deploy/remote.sh`
   with `FORCE=true` (there are no players).
8. Mint tokens: `docker compose exec server n3e-server admin mint --name ops --perm 'realm.*'`
   → `/etc/n3e-realm/ops.token`; `… --name bot --perm 'world.*' --perm 'account.*'
   --perm realm.status --perm realm.notice` → `.env` `REALM_ADMIN_TOKEN`; `docker compose
   up -d bot`.
9. (reserved)
10. Restore a backup if this is a rebuild (`zstd -d | psql`), **before** step 7's
    `migrate` if the dump is older than current migrations — i.e. restore first, then
    deploy.
11. Install the backup timer (`systemd` unit + timer in `deploy/systemd/`), run it once,
    verify the object appears.
12. Add the CD deploy key to `deploy`'s `authorized_keys`; set `VPS_HOST/USER/SSH_KEY`
    in GitHub Secrets; trigger `workflow_dispatch` and watch it go green.
13. Join the Discord and run `/status`.

Record every deviation in `HOST.md`.

### R2 — Rotate a secret

| Secret | Procedure |
|---|---|
| ops token | `mint --name ops-2 …` → write file → `revoke --name ops` → rename. Zero downtime. |
| bot token | `mint --name bot-2` → edit `.env` → `docker compose up -d bot` → `revoke --name bot`. |
| Discord bot token | Regenerate in the developer portal → `.env` → `up -d bot`. |
| OAuth secret | Regenerate → `.env` → gated `server` restart (`remote.sh --local`). |
| DB password | `ALTER ROLE`, `.env`, restart all (gated). |
| GitHub PAT | Regenerate (90-day) → `.env` → `up -d bot`. Calendar entry in `HOST.md`. |
| VPS ssh key | New key in GitHub Secrets → append pubkey → remove old. |

### R3 — Emergency: the realm is being hit

1. `/status` — if `connections.refused_*` are climbing and players are fine, the layers
   are working; do nothing.
2. If players can't connect and the provider's panel shows mitigation active: wait; it
   typically settles in minutes.
3. If it doesn't: lower `N3E_IP_MAX_CONCURRENT` to 1 and `N3E_IP_CONNECT_RATE` to 3 in
   `.env`, restart `server` with `FORCE=true` (the realm is unusable anyway).
4. If still bad: move the IP (origin hiding procedure) and open a ticket with the
   provider. Then read the ladder in `architecture.md`.

## Acceptance tests

1. R1 executed on a scratch VPS by someone other than the author, timed, ≤ 45 min,
   deviations folded back into this file.
2. `nmap` from outside shows only `22` and `7777`. `7780`, `8080`, `5432`, `6379` closed.
3. Certificate renewal dry-run (`certbot renew --dry-run`) runs the hook; with a test
   client connected, the hook **skips** the restart and sets `deploy_pending`-like
   evidence in the log; with none connected, it restarts and the new cert is served.
4. Backup timer produces an object; restore rehearsal passes on a scratch VM.
5. Secrets audit: `grep -r` of `/opt/n3e-realm` and the repo for the ops token: only
   `/etc/n3e-realm/ops.token`.
6. R3 step 3 performed in a drill: limits change takes effect; `/status` reflects it.

## Open questions

Q15, Q16.
