"""Isolated KO-05 two-actor NPC scenario with optional graphical observer."""

import json
import math
import os
from pathlib import Path
import re
import subprocess
import time
import uuid
from world_peer import Peer as BasePeer, fields, first
from isolation import DISPOSABLE_COMPOSE, container_logs

B = Path("build/ko-05")
B.mkdir(parents=True, exist_ok=True)
package = Path(os.environ.get("N3E_NPC_PACKAGE", "build/packages/npc")).resolve()
manifest = json.loads((package / "recipe.json").read_text())["manifest"]
content = (package / "release.sha256").read_text().strip()
project = "n3e-ko05-" + uuid.uuid4().hex[:10]
env = {
    **os.environ,
    "N3E_PORT": "0",
    "N3E_REALM": project,
    "N3E_PACKAGE_PATH": str(package),
    "N3E_UID": str(os.getuid()),
    "N3E_GID": str(os.getgid()),
}
base = ["docker", "compose", *DISPOSABLE_COMPOSE, "-p", project]
password = "test-only-" + uuid.uuid4().hex
peers = []


# The server keeps each strike's presentation event for this many ticks after
# the strike (server/src/presentation.rs Events::observe), and every World frame
# carries the events still kept, so frames at most this far apart miss none.
EVENT_TICKS = 40


class Peer(BasePeer):
    def __init__(self, *args, **kwargs):
        # The base constructor already reads frames (handshake, login).
        self.strikes = {}  # event sequence -> (actor, target, strike tick)
        self.frames = []  # World frame ticks, in arrival order
        super().__init__(*args, **kwargs)

    def receive(self):
        result = super().receive()
        if result[0] == 16:
            self.last_result = result[1]
        if result[0] == 10:
            self.frames.append(first(result[1], 1))
            for raw in result[1].get(14, []):
                e = fields(raw)
                if first(e, 5) == 2:  # strike
                    self.strikes[first(e, 1)] = (first(e, 3), first(e, 4), first(e, 2))
        return result


def dc(*args, stdin=None):
    p = subprocess.run(
        base + list(args),
        env=env,
        input=stdin,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert p.returncode == 0, (args, p.stdout, p.stderr)
    return p.stdout


def connect(name):
    p = Peer(
        port, name, password, content=content, game=manifest["game_id"], protocol=2
    )
    peers.append(p)
    return p


def health(p, id):
    return first(p.entities[id], 7)


def npc(p):
    return next(id for id, e in p.entities.items() if first(e, 9) and health(p, id))


def update(seconds=0.2):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        for peer in peers:
            if peer.s.fileno() >= 0 and peer.id:
                peer.send(14)
                peer.until(10)


def travel(peer, x, z):
    for _ in range(250):
        a = peer.entities[peer.id]
        dx, dz = x-first(a,3), z-first(a,5)
        d = math.hypot(dx,dz)
        if d < 0.2:
            return
        peer.move(dx/d, dz/d, mode=1)
        while first(peer.entities[peer.id],6) < peer.seq:
            update(0.01)
    raise AssertionError(("travel", x,z,peer.entities[peer.id]))


def behavior(peer, target):
    return first(peer.entities[target],12,b"").decode()


def cadence(peer, actor, target):
    """Successive strike ticks of `actor` on `target` that no unseen strike can
    separate: a pair is kept only if no two consecutive received frames between
    them lie more than EVENT_TICKS apart (World frames are latest-value, so a
    stalled reader can lose frames, never a kept event)."""
    ticks = sorted({t for a, b, t in peer.strikes.values() if (a, b) == (actor, target)})
    gaps = [(x, y) for x, y in zip(peer.frames, peer.frames[1:]) if y - x > EVENT_TICKS]
    return [(s, t) for s, t in zip(ticks, ticks[1:]) if not any(x < t and y > s for x, y in gaps)]


def wait_state(peer, target, wanted, seconds=15):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        update()
        if behavior(peer,target)==wanted:
            return
    raise AssertionError((wanted,peer.entities[target]))


graphics = None
try:
    dc("up", "--build", "-d", "--wait")
    port = int(dc("port", "server", "7777").strip().rsplit(":", 1)[1])
    for name in ["alpha", "beta", "observer"]:
        dc("exec", "-T", "server", "n3e-server", "account-create", name, stdin=password+"\n")
    if os.environ.get("N3E_GRAPHICAL") == "1":
        g=connect("observer"); g.create("Observer");g.s.close()
        log=B/f"{package.name}-graphics.log"
        with log.open("w") as output:
            graphics=subprocess.Popen(["build/client/n3e-test-client",str(package),"--connect",f"localhost:{port}","--ca","deploy/local/ca.pem","--auto-login","--npc-observe","70","--capture",str(B/f"{package.name}.ppm")],env={**os.environ,"N3E_TEST_ACCOUNT":"observer","N3E_TEST_PASSWORD":password},stdout=output,stderr=subprocess.STDOUT)
    if os.environ.get("N3E_NPC_DEATH_ONLY") == "1":
        p=connect("alpha");p.select(p.create("Alpha"))
        q=connect("beta");q.select(q.create("Beta"))
        target=npc(p)
        travel(p,-1,-1)
        old=p.id
        end=time.monotonic()+15
        while health(p,p.id)>0 and time.monotonic()<end:update()
        assert health(p,p.id)==0
        assert p.action(target)=="actor_dead"
        wait_state(q,target,"return")
        wait_state(q,target,"recover")
        update(2.5)
        assert p.id!=old and behavior(q,target)=="idle"
        print("PASS two-peer target death, rejected dead action, return and fresh respawn identity",flush=True)
    else:
        p=connect("alpha");character=p.create("Alpha");p.select(character)
        q=connect("beta");beta=q.create("Beta");q.select(beta)
        target=npc(p)
        update(1)
        assert behavior(p,target)=="idle"
        assert p.action(target,session=p.session+1)=="stale_session"
        assert p.action(target)=="out_of_range"
        travel(p,-1,-1)
        wait_state(p,target,"attack")
        # Sentinel swings hit 80 % (accuracy 50 against evasion 100), every 20
        # ticks: 2 s held exactly two swings after the first, failing one run in
        # 25 (PQ-123). Count swings (strike_tick, field 10), not seconds; 15
        # misses in a row is 0.2**15. The 60 s guard only catches a stall.
        # "Paced" (PQ-126): the server swings again exactly npc_cooldown_ticks
        # after each swing while the target stays in range (npc_ai.rs
        # next_attack), stamping strike_tick with the swing's tick, and logical
        # ticks never skip under load (simulation.rs), so every delta is exact.
        interval=manifest["gameplay"]["npc_cooldown_ticks"]
        before=health(p,p.id);seen=first(p.entities[target],10);shown={seen}-{0};swings=0;guard=time.monotonic()+60
        while health(p,p.id)>=before or len(cadence(p,target,p.id))<3:
            assert swings<15 and time.monotonic()<guard,("no sentinel damage or cadence",swings,cadence(p,target,p.id),p.entities[target])
            update(0.05)
            if first(p.entities[target],10)!=seen:seen=first(p.entities[target],10);shown.add(seen);swings+=1
        assert health(p,p.id)<before
        paced=cadence(p,target,p.id)
        assert all(t-s==interval for s,t in paced),("sentinel cadence",interval,paced)
        # Each strike_tick the snapshots showed is one of those event ticks.
        assert shown<={t for a,b,t in p.strikes.values() if a==target},(shown,p.strikes)
        print("PASS acquisition, chase, paced authoritative attacks",[t-s for s,t in paced],flush=True)
        travel(q,-1.3,-1.3)
        before=health(q,q.id)
        hits=0
        for _ in range(30):
            status=q.action(target)
            assert status in ("hit","miss","cooldown"), status
            hits+=status=="hit"
            update(1.05)
            if hits>=2 and health(q,q.id)<before:break
        assert hits>=2 and health(q,q.id)<before
        assert health(p,target)==health(q,target)
        print("PASS second actor repeated damage, retaliation and shared state",flush=True)
        q.logout()
        wait_state(p,target,"return")
        wait_state(p,target,"recover")
        assert health(p,target)==manifest["gameplay"]["npc_health"]
        wait_state(p,target,"attack")
        print("PASS target disconnect, return, home heal, recovery and reacquisition",flush=True)
        travel(p,0,9)
        wait_state(p,target,"recover")
        assert health(p,target)==manifest["gameplay"]["npc_health"]
        update(2.5)
        assert behavior(p,target)=="idle"
        print("PASS leash crossing and stable home reset",flush=True)
        # PQ-193 (D-152): the NPC neither picks, chases nor strikes a session the
        # server withholds (a current server.inspect lease) and does not turn on
        # it when it strikes; an ordinary player is still attacked; a revocation
        # makes it a target again (KO's AI skips an operator: AI 0041c21e,
        # 0041de51, 0041e628, 0041e9fd, 0041f715). q, an ordinary observer,
        # reconnects where it logged out and first walks out of aggro range.
        def role(grant):
            dc("exec","-T","server","n3e-server","role","grant" if grant else "revoke","alpha",str(character),project,"server.inspect")
        def calm(seconds):
            """Over `seconds`, the NPC (as q sees it) neither attacks nor chases and strikes no one."""
            last=first(q.entities[target],10);end=time.monotonic()+seconds
            while time.monotonic()<end:
                update()
                assert behavior(q,target) in ("idle","return","recover") and first(q.entities[target],10)==last,("NPC turned on a hidden operator",q.entities[target])
        def struck(peer,victim,since):
            """Strike events of the NPC on `victim` after tick `since` that `peer` received."""
            return [t for a,b,t in peer.strikes.values() if a==target and b==victim and t>since]
        def until_struck(peer,victim,since,seconds=15):
            end=time.monotonic()+seconds
            while not struck(peer,victim,since) and time.monotonic()<end:update()
            return struck(peer,victim,since)
        q=connect("beta");q.select(beta)
        travel(q,0,9);wait_state(q,target,"idle")
        travel(p,-1,-1);wait_state(q,target,"attack")
        role(True)
        wait_state(q,target,"idle")
        hidden_at=p.frames[-1];calm(3)
        assert not struck(p,p.id,hidden_at),"a hidden operator in range was struck"
        e=q.entities[target];travel(p,first(e,3)+0.5,first(e,5))
        npc_before=health(q,target);status=None
        for _ in range(10):
            status=p.action(target)
            assert status in ("hit","miss","cooldown"),status
            if status=="hit":break
            update(1.05)
        end=time.monotonic()+2
        while health(q,target)>=npc_before and time.monotonic()<end:update()
        assert status=="hit" and health(q,target)<npc_before,("hidden operator's strike",status,health(q,target),npc_before)
        calm(2)
        assert not struck(p,p.id,hidden_at),"the NPC turned on the hidden operator that struck it"
        print("PASS NPC ignores a hidden operator in range and does not turn on it when it strikes",flush=True)
        e=q.entities[target];since=q.frames[-1];travel(q,first(e,3)-0.5,first(e,5))
        wait_state(q,target,"attack")
        assert until_struck(q,q.id,since),"no strike on the ordinary player"
        assert not struck(p,p.id,hidden_at),"the hidden operator beside it was struck"
        print("PASS NPC still attacks an ordinary player beside a hidden operator",flush=True)
        travel(q,0,9);wait_state(q,target,"idle")
        assert not struck(p,p.id,hidden_at),"the hidden operator was struck"
        role(False);shown_at=p.frames[-1]
        wait_state(p,target,"attack")
        assert until_struck(p,p.id,shown_at),"no strike on the operator after the revoke"
        print("PASS NPC drops a target that becomes hidden and targets it again after the revoke",flush=True)
        travel(p,0,9);wait_state(q,target,"idle")
        # Reconnect cannot retain a stale runtime target identity.
        old=p.id;p.logout();p=connect("alpha");p.select(character)
        assert p.id!=old
        if graphics:
            while graphics.poll() is None:
                update(0.5)
            assert graphics.returncode==0,log.read_text()
            observed=set(re.findall(r"NPC state=(\w+)",log.read_text()))
            assert {"idle","chase","attack","return","recover"} <= observed,log.read_text()
            print("PASS graphical chase/attack/return/recovery capture",flush=True)

finally:
    if graphics and graphics.poll() is None:
        graphics.terminate();graphics.wait(timeout=5)
    for p in peers:p.s.close()
    # PQ-128: every service's log, before the stack is removed.
    container_logs("compose", [*base, "logs", "--no-color", "--timestamps"], env=env)
    (B/f"{package.name}-server.log").write_text(dc("logs","--no-color","server"))
    dc("down","-v","--remove-orphans")
