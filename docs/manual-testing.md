# Manual test round: Linux and Windows

The maintainer's periodic check of what the automated suites cannot do: a real
Discord login in a browser, the Discord bot in a real server, and the Windows client
on a real GPU (Q3). The realm runs on the Linux machine (the local Compose stack); the
Windows PC plays it over the LAN. About an hour the first time.

Record each step as pass or fail; for a failure, copy the console text (the game and
the launcher print to their terminal or console window) and what you saw.

## Once: the Discord application

The bot's application can also be the login application.

1. <https://discord.com/developers/applications> → the application → **OAuth2**.
   Under **Redirects** add all four:
   `http://127.0.0.1:49152/callback`, `http://127.0.0.1:49153/callback`,
   `http://127.0.0.1:49154/callback`, `http://127.0.0.1:49155/callback`. Save.
2. Copy the **Client ID**, and **Reset Secret** to get the client secret. Add both to
   `.env` (never commit it):

   ```
   DISCORD_CLIENT_ID=<client id>
   DISCORD_CLIENT_SECRET=<client secret>
   ```

## Once per round: the realm on the Linux machine

Use the machine's LAN address (`ip -4 addr`; below, `192.168.86.21`).

```sh
source tools/env.sh
make client server                       # the client and the server
make realm-assets                        # the KO tree (once) and build/packages/moradon
cargo build --release --locked -p realm-launcher
tools/local-realm 192.168.86.21          # stack on the LAN; the certificate names the address
```

`tools/local-realm` prints `realm test-local-<package hash> on port 7777 (LAN, …)`. For the bot, the
first time: mint its admin token, add it to `.env`, and run `tools/local-realm` again:

```sh
docker compose exec server n3e-server admin mint --name bot --perm world.catalog \
  --perm world.spawn --perm world.kill --perm world.event --perm 'account.*' \
  --perm realm.status --perm realm.notice
# .env: REALM_ADMIN_TOKEN=<the printed token>
tools/local-realm 192.168.86.21          # now also "bot started"
```

The database keeps the token; a new one is needed only after `docker compose down -v`.
`tools/local-realm down` stops everything.

## Linux: the player's path

In a second terminal, publish this tree as a release the launcher can install:

```sh
python tools/local_release.py            # serves http://127.0.0.1:8770 until Ctrl-C
```

In a third:

```sh
target/release/realm-launcher --add-realm local http://127.0.0.1:8770/manifest.json
target/release/realm-launcher --realm local --ca deploy/local/ca.pem
```

Against the realm on its host (`deploy/HOST.md`, `gn100`) instead of this machine's
stack: `python tools/local_release.py --host gn100-69be.local`, then the launcher with
`--ca build/gn100/ca.pem` (copied from the host's `deploy/local/ca.pem`). Run this
machine's `tools/local-realm` without its bot meanwhile: one bot per Discord token.

The window is 1280x1024; add `--fixed-window 1024x768` (or `1600x1200`) for another of
KO's sizes, and `--fullscreen` for full screen at that size (Q62).

| # | Do | Expect |
|---|---|---|
| L1 | The second command | `Downloading client …`, `Downloading content …`, `Starting Local Realm`; the game opens on KO's login screen: the orc with the axe under the moon, KO's copyright line, and the login bar exactly as KO's: ID and Password boxes, **Login**, **Cancel**, **Option**, **Registration** (only Login and Cancel do anything). KO's intro music plays and loops (RQ-018); with `[Sound] Effect=0` in the client's `Option.ini` (`~/.config/n3e/`, `%APPDATA%\n3e\` on Windows) the game is silent (Q70). |
| L2 | **Login** (or ENTER, even right after the window opens) | The browser opens Discord's authorize page for your application; after **Authorize** the tab says you are logged in, and KO's server list drops in from the top with "Local Realm". |
| L3 | Double-click the realm (or **Connect**) | The Karus character select hall. With no characters, ENTER opens character create (Tuarek priest, name field). |
| L4 | Type a name, **Create**; then ENTER (or click the character) | Back in the hall with the new character in the centre slot and "Level 1" in the info bar; ENTER plays its selected animation, then the loading screen, then the world. The intro music plays on without restarting through the realm list, select and create, and stops when the loading screen shows. |
| L5 | Walk and run | Moves as in the play scripts. |
| L6 | Close the game; run the launcher again | No downloads; the game logs in without the browser and opens on the server list. |
| L7 | Discord: `/status`; `/whois` and pick yourself | One player online; your account, its characters and session. |
| L8 | Discord: `/notice` some text | It appears in the game; the bot posts it to the announcements channel. |
| L9 | Discord: `/kick` yourself with a reason | The game returns to the login screen with a message box: "You were disconnected by an operator: <reason>."; the ops channel shows the kick by your name. |
| L10 | Discord: `/ban` yourself for 30m, then start the game | "Your account is blocked until … UTC: <reason>."; no login. |
| L11 | Discord: `/unban`, start the game | The browser flow again (a ban revokes the session), then logged in. |
| L12 | Discord: `/mute` yourself for 30m, chat in game; `/unmute`, chat again | The game refuses the chat line while muted (note its wording); it goes through after. |

## Windows: the client on a real GPU

On the Linux machine, once CI's `client` job has passed for the commit you are on
(the Actions tab), build the kit and copy it to the Windows PC:

```sh
python tools/windows_kit.py --host 192.168.86.21     # build/windows-kit.zip
```

It holds CI's `n3e-client.exe` and `realm-launcher.exe`, the Moradon package the
realm serves, `realm.json` naming `192.168.86.21:7777`, the local CA and three `.bat` files.
Unzip it anywhere on the Windows PC. Windows may say the files are from an unknown
publisher (they are unsigned, Q26): **More info → Run anyway**.

| # | Do | Expect |
|---|---|---|
| W1 | `self-test.bat` | Ends with `self-test ok`; its `opengl` line names your GPU, not `llvmpipe` or `GDI Generic`. |
| W2 | `play.bat`, **Login** | KO's login screen, as L1; the browser opens Discord; after **Authorize** the server list drops in. |
| W3 | Connect, create a character, enter the world, walk and run | As L3–L5; note the frame rate if it feels slow. |
| W4 | Close; `play.bat` again | Logs in without the browser and opens on the server list. |
| W5 | Discord: `/kick` yourself | Back on the login screen with the disconnect message box, as L9. |
| W6 | `forget-login.bat`, then `play.bat` | The browser flow again. |
| W7 | Command prompt in the kit: `realm-launcher.exe --version` | `realm-launcher … (windows-x86_64)`. |

If the game says it cannot connect, the Linux firewall is the usual cause. Docker
normally opens the published port past `ufw`; if not:
`sudo ufw allow from 192.168.86.0/24 to any port 7777 proto tcp`.

## Afterwards

`tools/local-realm down`. Report the table results. The full Windows launcher path
(download one binary, install from a published Release, play) waits for a published
Release (M5, or a test pre-release); W7 only shows the launcher runs.
