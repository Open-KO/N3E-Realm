#!/usr/bin/env python3
"""Play one KO homeland map on a persistent local stack of its own (PQ-218).

  tools/play-ko-zone karus          Breth, zone 1 (Zones.tbl key 10, karus2004)
  tools/play-ko-zone elmorad        Piana, zone 2 (Zones.tbl key 20, elmo2004)
  tools/play-ko-zone karus-1097     the 2003 Karus homeland (1097 key 1, karus_start)
  tools/play-ko-zone elmorad-1097   the 2003 El Morad homeland (1097 key 2, elmorad_start)

The map is cooked from the player's own KO data by `tools/assetc/ko_bake.py KEY`
(PQ-217) into build/packages/ko-zone-KEY, which needs the operator's own
START_POSITION export (--start-positions=PATH, default
build/ko-completion/database-parity/START_POSITION.json; never committed). Each
zone gets its own Compose project (n3e-ko-zone-KEY), port, server image tag,
`test-` realm (named for the cooked release, so a new cook gets a new realm and
fresh characters, as tools/play-moradon does) and state under
build/ko-zone-KEY-demo. The tools/play-moradon stack (project n3e-moradon) and
the default project are never touched. One zone per stack until zone transfer
(PQ-056).

The 1097 maps (PQ-274, D-170) are cooked by `ko_bake.py KEY --client=1097`
from the 1097 install's own zone files into build/packages/ko-1097-zone-KEY
(the player and HUD from the 2004 client data), with Compose project
n3e-ko-1097-zone-KEY, ports 7797/7798 and state under
build/ko-1097-zone-KEY-demo. When that install is not unpacked yet, the
player's ref/ko-bin/installer/KnightOnline_1097.exe is unpacked first by the
pinned tools/ko-reference/unpack_installer.py (nothing in it is run).

Population (PQ-219) changes only the bake: whatever the package carries is
served; the stack, accounts and launch stay as they are.
"""
import argparse, json, os, pathlib, re, secrets, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
os.chdir(ROOT)
# name -> (Zones.tbl key, default port, package, client); ports 7793/7794 and
# 7797/7798 are used by no other launcher.
ZONES = {"karus": (10, 7793, "ko-zone-10", None), "elmorad": (20, 7794, "ko-zone-20", None),
         "karus-1097": (1, 7797, "ko-1097-zone-1", "1097"), "elmorad-1097": (2, 7798, "ko-1097-zone-2", "1097")}
ALIASES = {"breth": "karus", "piana": "elmorad", "10": "karus", "20": "elmorad",
           "karus_start": "karus-1097", "elmorad_start": "elmorad-1097"}
INSTALLER_1097 = ROOT / "ref/ko-bin/installer/KnightOnline_1097.exe"
p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("zone", help="karus (Breth, key 10), elmorad (Piana, key 20), karus-1097 or elmorad-1097 "
                            "(the 1097 client's karus_start and elmorad_start, keys 1 and 2)")
p.add_argument("--companion", action="store_true", help="join the running stack as a second player, without restarting it")
p.add_argument("--reuse", action="store_true", help="join the running stack without rebuilding or restarting it")
p.add_argument("--no-build", action="store_true", help="use the already built client/server and cooked package")
p.add_argument("--provision-only", action="store_true", help="prepare the stack and credentials without opening a client")
p.add_argument("--start-positions", metavar="PATH", help="the operator's START_POSITION export for the bake")
raw = sys.argv[1:]
separator = raw.index("--") if "--" in raw else len(raw)
args = p.parse_args(raw[:separator])
client_args = raw[separator + 1:]
name = ALIASES.get(args.zone.lower(), args.zone.lower())
if name not in ZONES:
    p.error("the zone is karus (Breth), elmorad (Piana), karus-1097 or elmorad-1097, not %r" % args.zone)
key, default_port, package_name, client = ZONES[name]
work = ROOT / ("build/%s-demo" % package_name)
work.mkdir(parents=True, exist_ok=True)
package = ROOT / ("build/packages/%s" % package_name)
project = "n3e-%s" % package_name
env = os.environ.copy()
env.update(N3E_UID=str(os.getuid()), N3E_GID=str(os.getgid()), N3E_IMAGE="n3e-ko-zone:local",
           N3E_PACKAGE_PATH=str(package))
compose = ["docker", "compose", "-p", project]


def run(*cmd, input=None, capture=False):
    return subprocess.run(cmd, env=env, input=input, text=True, check=True, capture_output=capture)


def sql(query):
    return run(*compose, "exec", "-T", "postgres", "psql", "-U", "n3e", "-d", "n3e", "-At", "-v", "ON_ERROR_STOP=1",
               input=query, capture=True).stdout.strip()


def quote(value):
    return "'" + value.replace("'", "''") + "'"


def release():
    path = package / "release.sha256"
    if not path.is_file():
        raise SystemExit("No cooked package at %s; run tools/play-ko-zone %s without --no-build." % (package, name))
    return path.read_text().strip()


state_path = work / "session.json"
if args.reuse or args.companion:
    if not state_path.exists():
        raise SystemExit("Start tools/play-ko-zone %s once before joining it." % name)
    state = json.loads(state_path.read_text())
    env.update(N3E_PORT=str(state["port"]), N3E_REALM=state["realm"])
    if state["release"] != release():
        raise SystemExit("The cooked package changed; run tools/play-ko-zone %s to start its matching realm." % name)
else:
    if not args.no_build:
        run("make", "client", "server")
        if client == "1097" and not (ROOT / "build/ko-reference/installer-1097/manifest.json").is_file():
            if not INSTALLER_1097.is_file():
                raise SystemExit("The 1097 maps need your own KnightOnline_1097.exe at %s." % INSTALLER_1097)
            run(sys.executable, "-I", "tools/ko-reference/unpack_installer.py", str(INSTALLER_1097))
        run(sys.executable, "tools/assetc/ko_bake.py", str(key), *(["--client=" + client] if client else []),
            *(["--start-positions=" + args.start_positions] if args.start_positions else []))
    provenance = json.loads((ROOT / ("build/%s/provenance.json" % package_name)).read_text())
    nation = name.split("-")[0]
    if provenance.get("start", {}).get("nation") != nation or provenance["zone"].get("layout", "1298") != (client or "1298"):
        raise SystemExit("build/%s was not cooked with its %s START_POSITION start; "
                         "run without --no-build." % (package_name, nation))
    run("bash", "deploy/local-ca.sh")
    cooked = release()
    port = int(env.get("N3E_PORT", default_port))
    state = {"port": port, "realm": "test-%s-%s" % (package_name, cooked[:12]), "release": cooked, "zone": key,
             "project": project, "package": package_name}
    env.update(N3E_PORT=str(port), N3E_REALM=state["realm"])
    run(*compose, "build", "server")
    run(*compose, "up", "-d", "--wait", "postgres", "redis")
    run(*compose, "run", "--rm", "--no-deps", "migrate")
    # Stop only this zone's server, letting its lease drain before the conversion.
    run(*compose, "stop", "server")
    # The copied demo rules' reward policy is converted once per realm.
    if not sql("SELECT 1 FROM realm_reward_policy WHERE realm=" + quote(state["realm"]) + ";"):
        run(*compose, "run", "--rm", "--no-deps", "-e", "N3E_TEST_PROGRESSION=disposable", "server",
            "convert-progression")
    run(*compose, "up", "-d", "--wait", "--force-recreate", "server")
    state_path.write_text(json.dumps(state, indent=2) + "\n")

role = "companion" if args.companion else "explorer"
credentials = work / (role + ".json")
if credentials.exists():
    account = json.loads(credentials.read_text())
else:
    account = {"account": name.replace("-", "") + role + secrets.token_hex(4), "password": secrets.token_urlsafe(24)}
    with os.fdopen(os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
        json.dump(account, f)
# Insert-only: an account that exists keeps its characters; one whose database
# was removed (docker compose -p PROJECT down -v) is created again with the
# saved credentials.
if not sql("SELECT 1 FROM accounts WHERE name=" + quote(account["account"]) + ";"):
    run(*compose, "exec", "-T", "server", "n3e-server", "account-create", account["account"],
        input=account["password"] + "\n", capture=True)
sys.path.insert(0, str(ROOT / "tests"))
from world_peer import Peer  # noqa: E402
manifest = json.loads((package / "recipe.json").read_text())["manifest"]
peer = Peer(state["port"], account["account"], account["password"], content=state["release"],
            game=manifest["game_id"], protocol=manifest["protocol_version"])
if not peer.characters:
    peer.create("Companion" if args.companion else "Explorer")
character = peer.characters[0][0]
peer.s.close()
if role == "explorer":
    # Hold-Q turbo, granted by the server to this character in this realm only.
    run(*compose, "exec", "-T", "server", "n3e-server", "role", "grant", account["account"], str(character),
        state["realm"], "movement.turbo", capture=True)
title = {"karus": "Breth (Karus homeland, zone 1)", "elmorad": "Piana (El Morad homeland, zone 2)",
         "karus-1097": "karus_start (the 2003 Karus homeland, 1097 client key 1)",
         "elmorad-1097": "elmorad_start (the 2003 El Morad homeland, 1097 client key 2)"}[name]
print("%s: %s on localhost:%d, realm %s" % (title, role.title(), state["port"], state["realm"]), flush=True)
print("KO keys: W/S move, A/D turn, E auto-run, T walk/run, hold Q turbo, right-drag camera, M overview map.", flush=True)
print("Second player: tools/play-ko-zone %s --companion. Rejoin: tools/play-ko-zone %s --reuse." % (name, name), flush=True)
print("Stop: docker compose -p %s stop (down -v also removes its characters)." % project, flush=True)
if args.provision_only:
    sys.exit(0)
size = env.get("N3E_WINDOW_SIZE", "1280x1024")
# Supplied KO startup 0064b9b0 accepts these viewport modes (tools/play-moradon-preview).
if size not in ("1024x768", "1280x1024", "1600x1200"):
    raise SystemExit("N3E_WINDOW_SIZE must be 1024x768, 1280x1024 or 1600x1200")
# Automatic login is a test-client hook (PQ-006); the player n3e-client refuses it.
env.update(N3E_TEST_ACCOUNT=account["account"], N3E_TEST_PASSWORD=account["password"])
cmd = [str(ROOT / "build/client/n3e-test-client"), str(package), "--connect", "localhost:%d" % state["port"],
       "--ca", "deploy/local/ca.pem", "--auto-login", "--fixed-window", size,
       *(["--fullscreen"] if env.get("N3E_FULLSCREEN") == "1" else []), *client_args]
os.execve(cmd[0], cmd, env)
