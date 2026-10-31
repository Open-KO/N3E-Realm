#!/usr/bin/env python3
"""Disposable KO-11 review session. No existing realm or volume is modified."""
import argparse
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
import shlex

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "tests"))
from readiness import free_ports, wait_postgres
from isolation import DISPOSABLE_POSTGRES, container_logs
from world_peer import Budget, Peer, first, fields, integer, blob
import timescale

# The test warehouse password this session provisions, and the replacement its
# --storage-auth-check --graphical replay changes it to. The test client takes
# both from here (PQ-006); the player client knows no password.
STORAGE_SECRETS = {"N3E_TEST_STORAGE_PASSWORD": "Original_123",
                   "N3E_TEST_STORAGE_REPLACEMENT": "Replacement_123"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--package", choices=["demo", "demo-ko", "demo-alt"], default="demo"
    )
    parser.add_argument(
        "--check", action="store_true", help="exercise the actual package loop over TLS"
    )
    parser.add_argument(
        "--graphical",
        action="store_true",
        help="capture two logged-in graphical clients",
    )
    parser.add_argument(
        "--lifecycle",
        action="store_true",
        help="KO-12 two-peer audit with a narrow interest-grid fixture",
    )
    parser.add_argument(
        "--restart-check",
        action="store_true",
        help="KO-13 actual-package hard restart after saved death and claimed loot",
    )
    parser.add_argument("--tools",action="store_true",help="two tools clients; explorer gets scoped moderator capabilities")
    parser.add_argument("--chat-check", action="store_true", help="isolated three-peer private chat authority/privacy checks")
    parser.add_argument("--inventory-check",action="store_true",help="isolated durable inventory authority/recovery checks")
    parser.add_argument("--commerce-check",action="store_true",help="isolated merchant transactions and authority checks")
    parser.add_argument("--repair-check",action="store_true",help="isolated repair transactions and damaged item fixture")
    parser.add_argument("--equipment-check",action="store_true",help="isolated equipment authority and recovery checks")
    parser.add_argument("--stats-check",action="store_true",help="isolated equipment stats, combat and recovery checks")
    parser.add_argument("--wear-check",action="store_true",help="isolated ordinary durability combat and recovery checks")
    parser.add_argument("--storage-check",action="store_true",help="isolated account storage and recovery checks")
    parser.add_argument("--storage-auth-check",action="store_true",help="isolated protected warehouse credentials and recovery")
    parser.add_argument("--friends-check",action="store_true",help="isolated directed friends and presence recovery")
    parser.add_argument("--friends-full",action="store_true",help="include all item capabilities in the friend fixture")
    parser.add_argument("--party-check",action="store_true",help="isolated party membership and lifecycle")
    parser.add_argument("--party-rewards-check",action="store_true",help="isolated grouped XP and crash recovery")
    parser.add_argument("--reward-upgrade-check",action="store_true",help="preserving offline reward transition and old loot claims")
    parser.add_argument("--party-loot-check",action="store_true",help="isolated party item claims and rotation")
    parser.add_argument("--coin-loot-check",action="store_true",help="isolated generated coin drops and wallet recovery")
    parser.add_argument("--item-drops-check",action="store_true",help="isolated direct/group item bundles and durable recovery")
    args = parser.parse_args()
    if args.item_drops_check:args.party_check=True
    if args.coin_loot_check:args.party_check=True
    if args.party_loot_check:args.party_check=True
    if args.reward_upgrade_check:args.party_check=True
    if args.party_rewards_check:args.party_check=True
    if args.party_check:
        if args.friends_check or args.storage_check or args.storage_auth_check:parser.error("choose one feature fixture")
        args.storage_check=True
    if args.friends_full and not args.friends_check:parser.error("--friends-full requires --friends-check")
    if args.friends_check:
        if args.storage_check or args.storage_auth_check:parser.error("choose one feature fixture")
        args.storage_check=True
    if args.storage_auth_check:
        if args.storage_check:parser.error("choose one storage fixture")
        args.storage_check=True
    if args.storage_check:
        args.check=True
        if args.wear_check or args.stats_check or args.equipment_check or args.repair_check or args.commerce_check or args.inventory_check or args.chat_check or args.lifecycle or args.restart_check or args.package!="demo":parser.error("--storage-check uses its own fixture")
    if args.wear_check:
        args.check=True
        if args.stats_check or args.equipment_check or args.repair_check or args.commerce_check or args.inventory_check or args.chat_check or args.lifecycle or args.restart_check or args.package!="demo":parser.error("--wear-check uses its own fixture")
    if args.stats_check:
        args.check=True
        if args.equipment_check or args.repair_check or args.commerce_check or args.inventory_check or args.chat_check or args.lifecycle or args.restart_check or args.package!="demo":parser.error("--stats-check uses its own fixture")
    if args.equipment_check:
        args.check=True
        if args.repair_check or args.commerce_check or args.inventory_check or args.chat_check or args.lifecycle or args.restart_check or args.package!="demo":parser.error("--equipment-check uses its own fixture")
    if args.repair_check:
        args.check=True
        if args.commerce_check or args.inventory_check or args.chat_check or args.lifecycle or args.restart_check or args.package!="demo":parser.error("--repair-check uses its own fixture")
    if args.commerce_check:
        args.check=True
        if args.inventory_check or args.chat_check or args.lifecycle or args.restart_check or args.package!="demo":parser.error("--commerce-check uses its own fixture")
    if args.inventory_check:
        args.check=True
        if args.chat_check or args.lifecycle or args.restart_check or args.package != "demo": parser.error("--inventory-check uses its own fixture")
    if args.chat_check:
        args.check = True
        if args.lifecycle or args.restart_check or args.package != "demo":
            parser.error("--chat-check uses the original demo fixture independently")
    if args.restart_check:
        if args.lifecycle:
            parser.error("--restart-check uses the unchanged package, not --lifecycle")
        args.check = True
    if args.lifecycle:
        if args.package != "demo":
            parser.error("--lifecycle uses the original demo fixture")
        args.check = True
    package = (ROOT / "build/packages" / args.package).resolve()
    if args.lifecycle or args.chat_check:
        from session_lifecycle import prepare

        package = prepare()
    if args.inventory_check:
        from inventory_live import prepare
        package=prepare()
    if args.commerce_check:
        from commerce_live import prepare
        package=prepare()
    if args.repair_check:
        from repair_live import prepare
        package=prepare()
    if args.equipment_check:
        from equipment_live import prepare
        package=prepare()
    if args.stats_check:
        from stats_live import prepare
        package=prepare()
    if args.wear_check:
        from wear_live import prepare
        package=prepare()
    if args.storage_check:
        from storage_live import prepare
        package=prepare()
    if args.storage_auth_check:
        from storage_auth_live import prepare
        package=prepare()
    if args.friends_check:
        from friends_live import prepare
        package=prepare(full=args.friends_full)
    if args.party_check:
        from party_live import prepare
        package=prepare()
    if args.party_rewards_check:
        from party_rewards_live import prepare
        package=prepare()
    if args.party_loot_check:
        from party_loot_live import prepare
        package=prepare()
    if args.coin_loot_check:
        from coin_loot_live import prepare
        package=prepare()
    if args.item_drops_check:
        from item_drops_live import prepare
        package=prepare()
    if args.reward_upgrade_check:
        from reward_upgrades import prepare
        package=prepare()[0]
    manifest = json.loads((package / "recipe.json").read_text())["manifest"]
    out = ROOT / "build/ko-11" / args.package
    if args.lifecycle:
        out = ROOT / "build/ko-12/live"
    if args.chat_check:
        out = ROOT / "build/ko-completion/chat-live"
    if args.restart_check:
        out = ROOT / "build/ko-13" / args.package
    if args.inventory_check: out=ROOT/"build/ko-completion/items/live"
    if args.commerce_check: out=ROOT/"build/ko-completion/commerce/live"
    if args.repair_check: out=ROOT/"build/ko-completion/repair/live"
    if args.equipment_check: out=ROOT/"build/ko-completion/equipment/live"
    if args.stats_check: out=ROOT/"build/ko-completion/stats/live"
    if args.storage_check: out=ROOT/"build/ko-completion/storage/live"
    if args.wear_check: out=ROOT/"build/ko-completion/wear/live"
    if args.storage_auth_check:out=ROOT/"build/ko-completion/storage-auth/live"
    if args.friends_check:out=ROOT/("build/ko-completion/friends/live-full" if args.friends_full else "build/ko-completion/friends/live")
    if args.party_check:out=ROOT/"build/ko-completion/party/live"
    if args.party_rewards_check:out=ROOT/"build/ko-completion/party-rewards/live"
    if args.party_loot_check:out=ROOT/"build/ko-completion/party-loot/live"
    if args.reward_upgrade_check:out=ROOT/"build/ko-completion/reward-upgrades/live"
    if args.coin_loot_check:out=ROOT/"build/ko-completion/coin-loot/live"
    if args.item_drops_check:out=ROOT/"build/ko-completion/item-drops/live"
    out.mkdir(parents=True, exist_ok=True)
    if timescale.ACTIVE and (args.graphical or not args.check):
        # The client assumes 50 ms ticks (client/render/melee.h, player_pose.h,
        # hotbar.h); a window against a scaled server shows no real presentation.
        parser.error("graphical clients run at the production tick; unset N3E_LIVE_TICK_MS")
    name = "n3e-ko11-" + uuid.uuid4().hex[:10]
    password = "local-test-" + uuid.uuid4().hex
    containers = []
    peers = []
    graphics = []
    logs = []
    server = None
    env = dict(os.environ)
    server_binary = str(Path(env.get("N3E_TEST_SERVER", "target/debug/n3e-server")).resolve())

    def run(*cmd, stdin=None, good=True):
        p = subprocess.run(
            cmd, input=stdin, env=env, text=True, capture_output=True, timeout=120
        )
        if good and p.returncode:
            raise RuntimeError((cmd, p.returncode, p.stdout, p.stderr))
        return p

    def port():
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def connect(account, create=False, select=True):
        p = Peer(
            listen,
            account,
            password,
            content=(package / "release.sha256").read_text().strip(),
            game=manifest["game_id"],
            protocol=manifest["protocol_version"],
        )
        peers.append(p)
        if create:
            p.create(account.capitalize())
        if select:
            assert p.select(p.characters[0][0])[0] == 10
        return p

    def position(e):
        return tuple(first(e, k, 0.0) for k in (3, 5))

    observer = None

    def observe():
        if observer is not None:
            observer.pump(0.01)

    def walk(p, goal, tolerance=0.6, timeout=20):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            p.pump(0.05)
            observe()
            if not first(p.entities[p.id], 7):
                raise AssertionError("died while walking")
            x, z = position(p.entities[p.id])
            dx, dz = goal[0] - x, goal[1] - z
            d = math.hypot(dx, dz)
            if d < tolerance:
                return
            p.move(dx / d, dz / d, mode=1)
        raise AssertionError("walk timeout")

    def respawn(p):
        # Respawn sequences are per session; the death above may have used one.
        until = time.monotonic() + 20
        while first(p.entities[p.id], 16) != 3:
            assert time.monotonic() < until, ("respawn not ready", p.entities[p.id])
            p.pump(0.1)
            observe()
        p.respawns = getattr(p, "respawns", 0) + 1
        p.send(19, integer(1, p.session) + integer(2, p.respawns) + integer(3, p.id))
        assert first(p.until(20)[1], 2) == b"respawned"
        p.pump(0.2)

    def start_server(label):
        nonlocal server
        log = open(out / f"server-{label}.log", "w")
        logs.append(log)
        server = subprocess.Popen(
            [server_binary], env=env, stdout=log, stderr=log
        )
        for _ in range(100):
            if server.poll() is not None:
                raise RuntimeError((out / f"server-{label}.log").read_text())
            try:
                ready = urllib.request.urlopen(f"http://127.0.0.1:{health}/ready", timeout=0.2)
                if ready.status == 200:
                    # The waits below assume the tick the server reports (PQ-115).
                    timescale.confirm_health(ready.read().decode())
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise AssertionError("readiness timeout")

    try:
        for suffix, image, cp, extra in [
            (
                "",
                "postgres:17.4-bookworm@sha256:304ab813518754228f9f792f79d6da36359b82d8ecf418096c636725f8c930ad",
                5432,
                [
                    "-e",
                    "POSTGRES_USER=n3e",
                    "-e",
                    "POSTGRES_PASSWORD=test-only",
                    "-e",
                    "POSTGRES_DB=n3e",
                    *DISPOSABLE_POSTGRES,
                ],
            ),
            (
                "-redis",
                "redis:7.4.2-bookworm@sha256:fbdbaea47b9ae4ecc2082ecdb4e1cea81e32176ffb1dcf643d422ad07427e5d9",
                6379,
                [],
            ),
        ]:
            run(
                "docker",
                "run",
                "--rm",
                "-d",
                "--name",
                name + suffix,
                *extra,
                "-p",
                f"127.0.0.1::{cp}",
                image,
            )
            containers.append(name + suffix)
        pg = wait_postgres(name)
        redis = run("docker", "port", name + "-redis", "6379").stdout.strip()
        listen, health = free_ports(2)
        env.update(
            DATABASE_URL=f"host=127.0.0.1 port={pg} user=n3e password=test-only dbname=n3e",
            REDIS_ADDRESS=redis,
            N3E_REALM="test-" + name,
            N3E_PACKAGE=str(package),
            N3E_LISTEN=f"127.0.0.1:{listen}",
            N3E_HEALTH=f"127.0.0.1:{health}",
            N3E_TEST_PROGRESSION="disposable",
            # PQ-115: the scaled tick when tests/live.py asked for one.
            **timescale.server_env("test-" + name),
        )
        run(server_binary, "migrate")
        run(server_binary, "convert-progression")
        env.pop("N3E_TEST_PROGRESSION")
        accounts = ("explorer", "companion", "bystander") if args.chat_check or args.party_check else ("explorer", "companion")
        for account in accounts:
            run(
                server_binary,
                "account-create",
                account,
                stdin=password + "\n",
            )
        if args.storage_auth_check:
            for account in accounts:run(server_binary,"storage-password-init",account,stdin=STORAGE_SECRETS["N3E_TEST_STORAGE_PASSWORD"]+"\n")
        start_server("initial")
        for account in accounts:
            p = connect(account, True)
            if args.tools and account=="explorer":
                character=p.characters[0][0]
                for cap in ["world.edit","entity.spawn","server.inspect"]:
                    run(server_binary,"role","grant",account,str(character),env["N3E_REALM"],cap)
                review=ROOT/"build/p4/session.env";review.parent.mkdir(parents=True,exist_ok=True)
                review.write_text("".join("export "+k+"="+shlex.quote(v)+"\n" for k,v in {"DATABASE_URL":env["DATABASE_URL"],"N3E_REALM":env["N3E_REALM"],"N3E_REVIEW_CHARACTER":str(character)}.items()));review.chmod(0o600)
            p.logout()
            peers.remove(p)
        if args.inventory_check or args.commerce_check or args.repair_check or args.equipment_check or args.stats_check or args.wear_check or args.storage_check:
            if args.item_drops_check:
                from item_drops_live import audit
            elif args.coin_loot_check:
                from coin_loot_live import audit
            elif args.party_loot_check:
                from party_loot_live import audit
            elif args.reward_upgrade_check:
                from reward_upgrades_live import audit
            elif args.party_rewards_check:
                from party_rewards_live import audit
            elif args.party_check:
                from party_live import audit
            elif args.friends_check:
                from friends_live import audit
            elif args.storage_auth_check:
                from storage_auth_live import audit
            elif args.storage_check:
                from storage_live import audit
            elif args.wear_check:
                from wear_live import audit
            elif args.stats_check:
                from stats_live import audit
            elif args.equipment_check:
                from equipment_live import audit
            elif args.repair_check:
                from repair_live import audit
            elif args.commerce_check:
                from commerce_live import audit
            else:
                from inventory_live import audit
            def restart(compatibility=False,wear_fault=None,expected_exit=None,storage_fault=None,storage_auth_fault=None,friend_fault=None,settlement_fault=None,upgrade_package=None,upgrade_active=False,claim_fault=None):
                nonlocal server,package,manifest
                if upgrade_active:
                    saved=env["N3E_PACKAGE"];env["N3E_PACKAGE"]=str(upgrade_package)
                    try:rejected=run(server_binary,"upgrade-progression",str(package),good=False)
                    finally:env["N3E_PACKAGE"]=saved
                    assert rejected.returncode and 'realm already owned' in rejected.stderr,rejected.stderr
                    return
                if expected_exit is not None:assert server.wait(timeout=6)==expected_exit
                else:server.kill();assert server.wait(timeout=6)==-9
                server=None
                old_claim=env.pop("N3E_CLAIM_FAULT",None)
                if expected_exit==86 and old_claim:assert ("claim fault "+old_claim) in (out/("server-claim-"+old_claim+".log")).read_text()
                if claim_fault:env["N3E_CLAIM_FAULT"]=claim_fault
                env.pop("N3E_SETTLEMENT_FAULT",None)
                if settlement_fault:env["N3E_SETTLEMENT_FAULT"]=settlement_fault
                old_fault=env.pop("N3E_WEAR_FAULT",None)
                if expected_exit==94:assert old_fault and ("WEAR_FAULT "+old_fault) in (out/("server-wear-"+old_fault+".log")).read_text()
                old_storage=env.pop("N3E_STORAGE_FAULT",None)
                if expected_exit==95:assert old_storage and ("STORAGE_FAULT "+old_storage) in (out/("server-storage-"+old_storage+".log")).read_text()
                old_friend=env.pop("N3E_FRIEND_FAULT",None)
                if expected_exit==97:assert old_friend and ("FRIEND_FAULT "+old_friend) in (out/("server-friend-"+old_friend+".log")).read_text()
                if friend_fault:env["N3E_FRIEND_FAULT"]=friend_fault
                old_auth=env.pop("N3E_STORAGE_AUTH_FAULT",None)
                if expected_exit==96:assert old_auth and ("STORAGE_AUTH_FAULT "+old_auth) in (out/("server-storage-auth-"+old_auth+".log")).read_text()
                if storage_auth_fault:env["N3E_STORAGE_AUTH_FAULT"]=storage_auth_fault
                if storage_fault:env["N3E_STORAGE_FAULT"]=storage_fault
                if wear_fault:env["N3E_WEAR_FAULT"]=wear_fault
                for peer in peers: peer.s.close()
                peers.clear(); time.sleep(3.5)
                if upgrade_package:
                    previous=package;package=Path(upgrade_package)
                    manifest=json.loads((package/"recipe.json").read_text())["manifest"]
                    env["N3E_PACKAGE"]=str(package)
                    result=run(server_binary,"upgrade-progression",str(previous))
                    assert result.stdout.strip()=="reward upgrade revision 1",result.stdout
                    assert run(server_binary,"upgrade-progression",str(previous)).stdout==result.stdout
                if compatibility:
                    import hashlib
                    definition=hashlib.sha256((package/"inventory.bin").read_bytes()).hexdigest()
                    sql("UPDATE character_bags SET definition=decode(repeat('00',32),'hex')")
                    rejected=run(server_binary,good=False)
                    assert rejected.returncode and 'incompatible durable inventory' in rejected.stderr,rejected.stderr
                    sql("UPDATE character_bags SET definition=decode('"+definition+"','hex')")
                    print("PASS incompatible inventory definitions rejected before world admission",flush=True)
                start_server("claim-"+claim_fault if claim_fault else "settlement-"+settlement_fault if settlement_fault else "friend-"+friend_fault if friend_fault else "storage-auth-"+storage_auth_fault if storage_auth_fault else "storage-"+storage_fault if storage_fault else "wear-"+wear_fault if wear_fault else "inventory-recovered")
            def sql(command):
                return run("docker","exec",name,"psql","-U","n3e","-d","n3e","-v","ON_ERROR_STOP=1","-Atc",command).stdout
            if args.friends_check:audit(connect,restart,sql,full=args.friends_full)
            else:audit(connect,restart,sql)
            if args.graphical:
                if args.friends_check or args.party_check:friend_observer=connect("explorer")
                log=open(out/"inventory-client.log","w"); logs.append(log)
                client=subprocess.Popen(["build/client-tools/n3e-test-client" if args.tools else "build/client/n3e-test-client",str(package),"--connect",f"localhost:{listen}","--ca","deploy/local/ca.pem","--auto-login","--world-smoke","40" if args.party_loot_check or args.coin_loot_check else "20" if args.party_check else "15" if args.storage_auth_check or args.friends_check else "10" if args.wear_check or args.storage_check else "5","--capture",str(out/"inventory.ppm")],env={**env,**({"N3E_TEST_COIN_LOOT":"1"}if args.coin_loot_check else {"N3E_TEST_PARTY_LOOT":"1"}if args.party_loot_check else {}),"N3E_TEST_ACCOUNT":"companion","N3E_TEST_PASSWORD":password,**STORAGE_SECRETS,("N3E_TEST_PARTY" if args.party_check else "N3E_TEST_FRIENDS" if args.friends_check else "N3E_TEST_STORAGE_AUTH" if args.storage_auth_check else "N3E_TEST_STORAGE" if args.storage_check else "N3E_TEST_WEAR" if args.wear_check else "N3E_TEST_EQUIPMENT" if args.equipment_check or args.stats_check else "N3E_TEST_REPAIR" if args.repair_check else "N3E_TEST_COMMERCE" if args.commerce_check else "N3E_TEST_BAG"):"1"},stdout=log,stderr=log)
                graphics.append(client)
                if args.party_check:
                    from party_live import graphical_observer
                    if args.coin_loot_check:
                        from coin_loot_live import graphical_claim
                        graphical_observer(friend_observer,client,on_join=graphical_claim)
                    elif args.party_loot_check:
                        from party_loot_live import graphical_claim
                        graphical_observer(friend_observer,client,on_join=graphical_claim)
                    else:graphical_observer(friend_observer,client)
                if args.friends_check:
                    deadline=time.monotonic()+30
                    while client.poll()is None and time.monotonic()<deadline:friend_observer.pump(.2)
                code=client.wait(timeout=30); log.flush()
                assert code==0,("inventory graphical client",code,(out/"inventory-client.log").read_text())
                print("PASS inventory graphical replay",flush=True)
            return
        if args.chat_check:
            from chat_channels import audit
            audit(connect)
            return
        if args.check:
            p = connect("explorer")
            if args.lifecycle:
                from session_lifecycle import audit

                observer = connect("companion")
                p = audit(p, observer, connect)
            p.send(11, blob(1, "Hello from the demo"))
            assert first(p.until(11)[1], 1) == b"Hello from the demo"
            walk(p, (-3.5, -3.5))
            # Hit rolls decide this fight. Both sides hit 80 % and the sentinel
            # wins about one fight in 160-600 with the shipped demo stats
            # (evidence pq-123, Attempt 3); the check needs a kill, not a won
            # first fight, so a death respawns and fights again, at most five
            # fights. Resolved strikes bound it, not time; the guard only
            # catches a stall (PQ-123).
            fight = Budget("no XP", strikes=60, guard=240)
            lives = 5
            last_action = 0
            while first(p.inventory, 4) == 0 and fight.ok(p.entities):
                p.pump(0.1)
                observe()
                if not first(p.entities[p.id], 7):
                    lives -= 1
                    assert lives, ("demo player died in five fights before a kill", fight.last)
                    respawn(p)
                    walk(p, (-3.5, -3.5))
                    continue
                enemies = [
                    (id, e)
                    for id, e in p.entities.items()
                    if first(e, 9) and first(e, 7)
                ]
                if enemies and time.monotonic() - last_action > 1.05:
                    me = position(p.entities[p.id])
                    id, e = min(
                        enemies, key=lambda pair: math.dist(me, position(pair[1]))
                    )
                    fight.result(p.action(id))
                    last_action = time.monotonic()
            xp = first(p.inventory, 4)
            p.send(23)
            drops = [fields(v) for v in p.until(24)[1].get(1, [])]
            assert drops, "no durable drop"
            d = drops[0]
            p.send(
                25,
                integer(1, p.session)
                + integer(2, 1)
                + integer(3, p.id)
                + integer(4, first(d, 1))
                + integer(5, first(d, 2))
                + blob(6, first(d, 3))
                + integer(7, 1),
            )
            while True:
                result = p.until(26)[1]
                if first(result, 2) != b"pending":
                    break
            assert first(result, 2) == b"claimed", result
            p.pump(0.2)
            assert first(p.inventory, 2) == 1
            # Remain in aggro range without attacking: actual death and requested respawn.
            dead_id = p.id
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                p.pump(0.1)
                observe()
                if first(p.entities[p.id], 16) == 3:
                    break
            else:
                raise AssertionError("death/eligibility timeout")
            if observer is not None:
                observe()
                assert first(observer.entities[dead_id], 7) == 0
                assert first(observer.entities[dead_id], 16) in (2, 3)
                saved_position = position(p.entities[p.id])
                saved_session = p.session
                p.logout()
                peers.remove(p)
                p = connect("explorer")
                assert p.id != dead_id and p.session > saved_session
                assert first(p.entities[p.id], 16) == 3
                assert position(p.entities[p.id]) == saved_position
                assert first(p.inventory, 2) == 1 and first(p.inventory, 4) == xp
                observe()
                assert dead_id not in observer.entities and p.id in observer.entities
                dead_id = p.id
                print(
                    "PASS KO-12 saved death/eligibility/location and XP/item survive reconnect",
                    flush=True,
                )
            if args.restart_check:
                saved_position = position(p.entities[p.id])
                saved_session = p.session
                # These outcomes have already been acknowledged over verified TLS.
                server.kill()
                assert server.wait(timeout=6) == -9
                server = None
                for peer in peers:
                    peer.s.close()
                peers.clear()
                time.sleep(3.5)  # Let the old realm lease expire before takeover.
                start_server("recovered")
                p = connect("explorer")
                assert p.id != dead_id and p.session > saved_session
                assert first(p.entities[p.id], 16) == 3
                assert position(p.entities[p.id]) == saved_position
                assert first(p.inventory, 2) == 1 and first(p.inventory, 4) == xp
                p.send(27, integer(1, first(d, 1)))
                recovered = p.until(26)[1]
                assert first(recovered, 2) == b"claimed", recovered
                dead_id = p.id
                print(
                    "PASS KO-13 SIGKILL: saved death/location, XP, count and immutable claim recovered",
                    flush=True,
                )
            respawn(p)
            assert (
                p.id != dead_id
                and first(p.entities[p.id], 7) == manifest["gameplay"]["health"]
            )
            if observer is not None:
                observe()
                assert dead_id not in observer.entities and p.id in observer.entities
            before_reconnect = p.id, p.session
            p.logout()
            peers.remove(p)
            p = connect("explorer")
            assert first(p.inventory, 2) == 1 and first(p.inventory, 4) == xp
            if observer is not None:
                observe()
                assert p.id != before_reconnect[0] and p.session > before_reconnect[1]
                assert (
                    p.id in observer.entities
                    and before_reconnect[0] not in observer.entities
                )
                observer.logout()
                peers.remove(observer)
                observer = None
                print(
                    "PASS KO-12 observer death/respawn replacement and reconnect with committed XP/item",
                    flush=True,
                )
            p.logout()
            peers.remove(p)
            print(
                "PASS actual package: chat, run, hostile combat, XP, owner claim, death, Enter respawn, reconnect durability",
                flush=True,
            )
        if args.graphical or not args.check:
            for account in ("explorer", "companion"):
                log = open(out / f"{account}.log", "w")
                logs.append(log)
                command = [
                    "build/client-tools/n3e-test-client" if args.tools else "build/client/n3e-test-client",
                    str(package),
                    "--connect",
                    f"localhost:{listen}",
                    "--ca",
                    "deploy/local/ca.pem",
                    "--auto-login",
                ]
                if args.graphical:
                    command += [
                        "--world-smoke",
                        "4",
                        "--capture",
                        str(out / f"{account}.ppm"),
                    ]
                graphics.append(
                    subprocess.Popen(
                        command,
                        env={
                            **env,
                            "N3E_TEST_ACCOUNT": account,
                            "N3E_TEST_PASSWORD": password,
                        },
                        stdout=log,
                        stderr=log,
                    )
                )
            if args.tools:print("~ toggles the terminal (help, scene, list, get, set, publish); F11 opens the world editor sliders and handles. Explorer may publish; Companion has local drafts only. Operator revocation environment: source build/p4/session.env",flush=True)
            print(
                "Two clients: Z target, R attack, F claim, Enter respawn or chat. Close both to remove this disposable session.",
                flush=True,
            )
            for client in graphics:
                code = client.wait(timeout=30 if args.graphical else None)
                assert code == 0, code
    finally:
        for client in graphics:
            if client.poll() is None:
                client.terminate()
                client.wait(timeout=5)
        for p in peers:
            p.s.close()
        if server and server.poll() is None:
            server.terminate()
            server.wait(timeout=10)
        for log in logs:
            log.close()
        # PQ-128: each container's log, before it is removed.
        for container in containers:
            container_logs({name: "postgres", name + "-redis": "redis"}[container],
                           ["docker", "logs", "--timestamps", container])
        for container in reversed(containers):
            run("docker", "rm", "-f", container, good=False)


if __name__ == "__main__":
    main()
