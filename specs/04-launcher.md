# 04 — Launcher and Release manifest

Implements flow ⓪ and ⑨, Pushback #5 and #6 from `architecture.md`.

## Purpose

The only thing a player downloads by hand. It keeps the client binary and content
package current from GitHub Releases, verifies them, and starts the client. It is
intentionally tiny and boring because it also updates itself.

## Scope

In: manifest format; fetch/verify/install of launcher, client, content; self-update;
starting the client; surfacing "update required"; realm profiles. Out: authentication
(the client does the Discord flow, spec 02; the Launcher only hands it the realm config); a UI beyond a small progress window / console; mods; settings; multiple
realms (one realm is hardcoded by hostname; a second realm is a second manifest URL).

## Interfaces

### Manifest

Published as the Release asset `manifest.json`. The default realm profile fetches
`https://github.com/<org>/N3E-Realm/releases/latest/download/manifest.json` (public
repo; the repo **must** be public — Pushback #5). A fork's realm points at its own URL.

```json
{
  "schema": 1,
  "release": "2026.10.30-abc1234",
  "published_at": "2026-10-30T05:00:00Z",
  "realm": {
    "id": "n3e-realm", "name": "N3E Realm",
    "host": "play.example.org", "port": 7777,
    "discord_client_id": "123456789012345678",
    "news_url": "https://<pages>/news.md"
  },
  "launcher": {
    "version": "0.3.1",
    "min_version": "0.3.0",
    "artifacts": {
      "linux-x86_64": { "url": "…/realm-launcher-linux-x86_64", "sha256": "…", "size": 4194304 }
    }
  },
  "client": {
    "version": "2026.10.30-abc1234",
    "artifacts": {
      "linux-x86_64": { "url": "…/n3e-client-linux-x86_64.tar.zst", "sha256": "…", "size": 0 }
    }
  },
  "content": {
    "game": "moradon",
    "hash": "…64 hex sha256(release.bin)…",
    "index_url": "…/content-<hash>.index.json", "index_sha256": "…",
    "base_url": "…/content-files/"
  }
}
```

`content.index.json` (one per package, immutable, named by package hash):

```json
{
  "schema": 1, "hash": "…package hash…",
  "files": [
    { "path": "release.bin",        "sha256": "…", "size": 1234 },
    { "path": "assets/ironfang.bin","sha256": "…", "size": 4194304 }
  ]
}
```

Files are fetched from `base_url + sha256` (content-addressed; a file shared by two
package versions is stored and downloaded once). CD uploads only files not already
present (spec 06). The Launcher downloads only files it does not already have in its
local store.

- `schema` is bumped only on incompatible changes; a Launcher refusing an unknown
  schema must say "update the launcher manually" with the Releases URL.
- `platform` keys: `linux-x86_64`, `windows-x86_64`. `macos-aarch64` is not v1.
- `content.hash` is the identity the `Handshake.content` carries. It is **not** derivable
  from the file list alone (it is `sha256(release.bin)`), so the Launcher verifies it by
  hashing the installed `release.bin` after assembling the package.
- `realm.discord_client_id` is passed to the client; the OAuth flow is per Discord
  application and must not be compiled into the client.
- `launcher.min_version`: a Launcher older than this must self-update before doing
  anything else.

### Realm profiles

`$XDG_CONFIG_HOME/n3e-realm/realms.json`:
```json
{ "default": "n3e-realm",
  "realms": { "n3e-realm": { "manifest": "https://github.com/<org>/N3E-Realm/releases/latest/download/manifest.json" },
              "my-fork":   { "manifest": "https://example.org/realm/manifest.json" } } }
```
Ships with the default profile. `realm-launcher --realm my-fork` or `--add-realm NAME URL`.
The profile key is the Launcher's name for it; `manifest.realm.id` must match on first
use and is then pinned (a manifest that changes `id` is refused — it stops a hijacked
URL from silently re-pointing a profile).

### Install layout (Linux)

```
$XDG_DATA_HOME/n3e-realm/
  launcher/current -> launcher/<version>/realm-launcher
  client/<client.version>/n3e-client
  store/<sha256>                            # content-addressed file store, shared by all realms
  realms/<realm.id>/
    content/<content.hash>/                 # assembled package: hard links into store/
    realm.json                              # {host, port, discord_client_id, name} for the client
    manifest.json                           # last manifest successfully applied
    state.json                              # {installed: {client, content}, etag, last_check}
$XDG_CACHE_HOME/n3e-realm/downloads/        # partial downloads
```

Keep the **two** most recent client versions and content hashes per realm; prune
`store/` entries no assembled package references.

### CLI

```
realm-launcher [--realm NAME]       # normal: update if needed, start client
realm-launcher --check              # print what would change, exit 0/1, no changes
realm-launcher --no-update          # start whatever is installed (offline play / debugging)
realm-launcher --add-realm NAME URL # add a profile
realm-launcher --manifest URL       # one-off manifest URL (dev realms; not saved)
realm-launcher --ca PATH            # pass through to the client (dev only)
```

Exit codes: `0` client exited normally; `10` network error with nothing installed;
`11` verification failed; `12` manifest schema unsupported; `20` client exited with
"update required" and the Launcher could not fetch a newer manifest (realm ahead of
Releases — this is a CD ordering bug, say so).

### Starting the client

```
n3e-client <content dir> --realm <realms/<id>/realm.json> [--ca PATH]
```

The first positional is the content package directory (client convention). `--realm`
replaces `--connect`: the client reads host, port and `discord_client_id` from it (and
keeps `--connect` for dev). The Launcher passes nothing about authentication; the
client owns `session.json` (spec 02).

Client exit codes the Launcher recognises: `0` normal; `3` "update required"
(handshake refused with `VERSION` or `CONTENT`) — proposed convention, see Q10. On
`3`, the Launcher re-fetches the manifest once; if it changed, update and restart the
client once; if not, exit `20` with a clear message.

## Behaviour

1. **Self-check.** Read `state.json`. If the running binary's version < the last
   applied manifest's `launcher.min_version`, do the self-update first (step 3).
2. **Fetch manifest.** `GET` with `If-None-Match` from `state.json`. On 304 or network
   failure with something installed: proceed with what is installed, print a one-line
   warning. On network failure with nothing installed: exit `10`.
3. **Self-update.** If `launcher.version` > running version: download to
   `downloads/`, verify sha256 + size, `chmod 755`, place under `launcher/<v>/`, swap
   the `current` symlink atomically, re-exec the new binary with the same argv. Never
   update the launcher *and* the client in one process life — re-exec first.
4. **Client.** If `client.version` not installed: download, verify, extract into
   `client/<v>/` (extract to a temp dir, then rename).
5. **Content.** If `content.hash` not installed: fetch `index.json`, verify
   `index_sha256`; for each file not in `store/`, download `base_url + sha256`, verify,
   place in `store/`; assemble `content/<hash>/` by hard-linking (copy if the FS can't);
   finally verify `sha256(release.bin) == content.hash`. Mismatch → delete the assembled
   dir, exit `11`. Downloads run 4-wide.
6. **Commit.** Write `manifest.json` and `state.json` only after 4 and 5 succeed.
7. **Prune.** Remove client/content versions beyond the two newest.
8. **Start client**, wait, map exit code as above.

Downloads: resume with `Range` if a partial exists and the server supports it; otherwise
restart. Retry 3× with backoff. Always verify after download; never trust a partial.
Progress to stdout (and a minimal window if a GUI toolkit is cheap — not required).

## Failure modes

| Situation | Behaviour |
|---|---|
| GitHub down, everything installed | Start with installed versions, warn. |
| GitHub down, nothing installed | Exit 10 with the Releases URL. |
| Realm restarted with a newer package before the Release was published | Client exits 3; Launcher re-fetches; nothing new → exit 20 "realm is ahead of Releases; CD ordering bug". |
| Disk full mid-extract | Temp dir cleanup; exit 11. `state.json` untouched, so the previous version still works. |
| Launcher self-update binary fails to exec | Keep the old `current`; print the manual download URL. The symlink swap happens only after a successful `--version` of the new binary. |
| Two launchers run at once | `flock` on `$XDG_DATA_HOME/n3e-realm/lock`; the second says "already running" and exits 0 after starting nothing. |

## Security

- TLS to GitHub via the system CA store; no pinning.
- Every artifact's sha256 and size are verified **before** extraction or exec.
- Index paths are validated: relative, no `..`, no symlinks; files are written only
  under the assembled package dir.
- The Launcher never reads `session.json`.
- No telemetry.

## Build

Single static binary per platform: Rust, `x86_64-unknown-linux-musl` and
`x86_64-pc-windows-msvc`. No runtime deps. Unsigned for now (Q26); the player docs
explain the SmartScreen prompt. Windows paths: `%LOCALAPPDATA%\n3e-realm\` for data and
cache, `%APPDATA%\n3e-realm\` for config, replacing the XDG dirs above.

`--no-start` assembles/updates everything and exits 0 without starting the client (used
by CI's smoke job).

## Acceptance tests

1. **Clean install.** Empty XDG dirs, run the launcher against a test manifest: client
   and content land in the layout above; the client starts with the right argv.
2. **No-op.** Run again: no downloads (304), client starts within 1 s.
3. **Content update.** Publish a manifest whose package differs in two files: exactly
   two files are downloaded; the old package is kept; after a third version the oldest
   is pruned and `store/` entries only it referenced are removed.
4. **Corrupt artifact.** Serve an archive with a wrong sha256 → exit 11, nothing
   changed, previous version still starts with `--no-update`.
5. **Self-update.** Manifest with a newer `launcher.version` → the process re-execs;
   `realm-launcher --version` reports the new one; the client still starts.
6. **min_version.** Manifest with `min_version` above the running launcher and a
   broken launcher artifact → exit with the manual URL, no client start.
7. **Realm ahead.** Client exits 3 with an unchanged manifest → exit 20 with the
   ordering message.
8. **Offline.** Block network; `realm-launcher` starts the installed client; `--check`
   exits non-zero with a network message.
9. **Path safety.** An index entry with `../x` or an absolute path → rejected, exit 11.
10. **Lock.** Two concurrent launches → one client process.
11. **Profiles.** `--add-realm` a second manifest; `--realm` it; the client receives that
    realm's `realm.json`; a manifest whose `realm.id` changes is refused.

## Open questions

Q10, Q26.
