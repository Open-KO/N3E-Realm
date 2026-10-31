"""PQ-405 (D-208): a server refusal names the request it answers (Error.request,
the request's Envelope field number), and the test client shows it only on that
feature's status line.

Disposable Postgres and Redis, the native server, and the party fixture with every
item and social feature (inventory, storage with its credential, friends, party;
tests/party_live.py prepare(full=True)). Over real TLS a peer draws one refusal
from each request kind the server refuses in the simulation or the connection
handler and reads the request each names; a request-less refusal names 0. The
graphical branch (N3E_GRAPHICAL=1, make live) runs the test client's
N3E_TEST_REFUSALS replay: a movement refusal leaves the bag, storage, friends and
party lines as they were, while a bag and a party refusal reach only their own.
PQ-406 (D-209): the same replay then sends an empty Chat and a PrivateMessage to
an absent name; each refusal becomes the world's notice and is drawn on the HUD's
message line, while the feature lines and the chat line stay as they were.
PQ-407 (D-210): the message line keeps the demo HUD's two rows, each refusal in
the package's refusal colour; a client notice then takes the newest row in its
notice colour and the chat refusal, the oldest, leaves the rows.
PQ-408 (D-211): the demo HUD's scroll bar (12 messages, 6 lines, steps 1 and 2)
through the client's own pointer path: the up button steps back on release, a
message leaves a view that is off the bottom, a press below the thumb pages to
the bottom, more messages drop the lines past 6 while the view follows, a thumb
drag to the top shows the oldest kept lines, a message at the top drops none,
and the down button held past its delay repeats to the bottom.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

from isolation import DISPOSABLE_POSTGRES, container_logs
from party_live import prepare
from readiness import free_ports, wait_postgres
from world_peer import Peer, blob, first, integer

B = Path("build/pq405/live")
B.mkdir(parents=True, exist_ok=True)
package = prepare(full=True)
manifest = json.loads((package / "recipe.json").read_text())["manifest"]
for feature in ("inventory", "storage", "storage_auth", "friends", "party"):
    assert feature in manifest, feature
name = "n3e-pq405-" + uuid.uuid4().hex[:10]
realm = "test-" + name
password = "test-only-" + uuid.uuid4().hex
env = dict(os.environ)
containers, peers, logs, graphics = [], [], [], []
server = None
PASS = ("PASS client refusal routing: a movement refusal left the bag, storage, friends and party lines; "
        "the bag and party refusals reached only their own line; "
        "the chat and private message refusals reached only the HUD message line, "
        "which kept the newest two messages, refusals in the package's refusal colour and a client notice in its notice colour")
SCROLL = ("PASS client message scroll-back: the up button stepped back on release, a message left a view off the bottom, "
          "a page reached the bottom, the lines past the package's limit went while following, a thumb drag showed the "
          "oldest kept lines, a message at the top dropped none and a held down button repeated to the bottom after its delay")


def run(*cmd, good=True, stdin=None):
    p = subprocess.run(cmd, env=env, input=stdin, capture_output=True, text=True, timeout=120)
    assert not good or p.returncode == 0, (cmd, p.returncode, p.stdout, p.stderr)
    return p


def start():
    global server
    log = open(B / "server.log", "w")
    logs.append(log)
    server = subprocess.Popen(["target/debug/n3e-server"], env=env, stdout=log, stderr=log)
    for _ in range(100):
        assert server.poll() is None, (B / "server.log").read_text()
        try:
            if urllib.request.urlopen(f"http://127.0.0.1:{health}/ready", timeout=0.2).status == 200:
                return
        except OSError:
            time.sleep(0.05)
    raise AssertionError("server not ready")


def connect(account):
    p = Peer(listen, account, password, content=(package / "release.sha256").read_text().strip(),
             game=manifest["game_id"], protocol=manifest["protocol_version"])
    peers.append(p)
    if not p.characters:
        p.create(account.capitalize())
    assert p.select(p.characters[0][0])[0] == 10
    p.pump(0.2)
    return p


def refusal(p, tag, payload=b""):
    """Send one request and return the Error it draws: (code, request, detail)."""
    p.send(tag, payload)
    _, e = p.until(4)
    return first(e, 1), first(e, 3), first(e, 2, b"").decode()


try:
    for container, image, container_port, extra in [
        (name, "postgres:17.4-bookworm@sha256:304ab813518754228f9f792f79d6da36359b82d8ecf418096c636725f8c930ad", 5432,
         ["-e", "POSTGRES_USER=n3e", "-e", "POSTGRES_PASSWORD=test-only", "-e", "POSTGRES_DB=n3e", *DISPOSABLE_POSTGRES]),
        (name + "-redis", "redis:7.4.2-bookworm@sha256:fbdbaea47b9ae4ecc2082ecdb4e1cea81e32176ffb1dcf643d422ad07427e5d9", 6379, []),
    ]:
        run("docker", "run", "--rm", "-d", "--name", container, *extra, "-p", f"127.0.0.1::{container_port}", image)
        containers.append(container)
    pg = wait_postgres(name)
    redis = run("docker", "port", name + "-redis", "6379").stdout.strip()
    listen, health = free_ports(2)
    env.update(DATABASE_URL=f"host=127.0.0.1 port={pg} user=n3e password=test-only dbname=n3e",
               REDIS_ADDRESS=redis, N3E_REALM=realm, N3E_PACKAGE=str(package),
               N3E_LISTEN=f"127.0.0.1:{listen}", N3E_HEALTH=f"127.0.0.1:{health}")
    # The fixture's progression policy needs the disposable offline conversion.
    env["N3E_TEST_PROGRESSION"] = "disposable"
    run("target/debug/n3e-server", "migrate")
    run("target/debug/n3e-server", "convert-progression")
    env.pop("N3E_TEST_PROGRESSION")
    for account in ("explorer", "client"):
        run("target/debug/n3e-server", "account-create", account, stdin=password + "\n")
    start()
    p = connect("explorer")
    # Each refusal names the request it answers; the simulation's (movement,
    # party, friend presence, chat) and the connection handler's (bag, storage
    # credential) alike.
    for want, tag, payload in [
        ((3, 9), 9, integer(1, 0) + integer(2, 1)),  # stale session: INVALID_MOVEMENT
        ((4, 32), 32, integer(4, 1)),  # a listing with a source: invalid bag request
        ((4, 42), 42, b""),  # party sequence 0
        ((4, 40), 40, b""),  # friend presence sequence 0
        ((4, 11), 11, b""),  # empty chat line
        ((4, 36), 36, integer(1, 99)),  # storage credential operation 99
    ]:
        code, request, detail = refusal(p, tag, payload)
        assert (code, request) == want, (tag, code, request, detail)
    # A message the session does not accept answers no request: 0.
    code, request, detail = refusal(p, 5, blob(1, "explorer") + blob(2, password))
    assert (code, request) == (5, 0), (code, request, detail)
    p.logout()
    peers.remove(p)
    print("PASS server refusals name the request they answer: Move 9, BagRequest 32, PartyRequest 42, "
          "FriendPresenceQuery 40, Chat 11, StorageAuthRequest 36; a request-less refusal names 0", flush=True)
    # N3E_GRAPHICAL=1 is how tests/live.py (make live, the gate) selects every
    # suite's graphical branch (PQ-116); --graphical keeps the direct invocation.
    if "--graphical" in sys.argv or os.environ.get("N3E_GRAPHICAL") == "1":
        connect("client").logout()
        peers.clear()
        log = open(B / "client.log", "w")
        logs.append(log)
        graphics.append(subprocess.Popen(
            ["build/client/n3e-test-client", str(package), "--connect", f"localhost:{listen}",
             "--ca", "deploy/local/ca.pem", "--auto-login", "--world-smoke", "12",
             "--capture", str(B / "client.ppm")],
            env={**env, "N3E_TEST_ACCOUNT": "client", "N3E_TEST_PASSWORD": password, "N3E_TEST_REFUSALS": "1"},
            stdout=log, stderr=subprocess.STDOUT))
        code = graphics[0].wait(timeout=60)
        log.flush()
        text = (B / "client.log").read_text()
        assert code == 0 and PASS in text, (code, text[-4000:])
        print(next(line for line in text.splitlines() if line.startswith("REFUSAL movement")), flush=True)
        notices = [line for line in text.splitlines() if line.startswith("REFUSAL notice")]
        assert [n.split("'")[1] for n in notices] == ["chat length/rate", "private message recipient unavailable",
                                                     "Unavailable: Camera mode selection is not implemented."], notices
        # PQ-407 (D-210): the demo HUD's two message rows and their colours
        # (refusal ffffd060, notice ffa0d0ff), as the client drew them.
        assert notices[-1].endswith(" rows ['private message recipient unavailable' ffffd060]"
                                    " ['Unavailable: Camera mode selection is not implemented.' ffa0d0ff]"), notices[-1]
        for line in notices:
            print(line, flush=True)
        # PQ-408 (D-211): the scroll bar, stage by stage, as the client drew it.
        scroll = {line.split()[2]: line for line in text.splitlines() if line.startswith("REFUSAL scroll ")}
        assert list(scroll) == ["follow", "up", "off-bottom", "page", "limit", "drag", "top", "hold"], list(scroll)
        refusal = lambda t: f"['{t}' ffffd060]"
        notice = lambda t: f"['{t}' ffa0d0ff]"
        client = "Unavailable: Camera mode selection is not implemented."
        test = lambda n: f"Unavailable: Scroll test {n} is not implemented."
        older = " rows " + refusal("chat length/rate") + " " + refusal("private message recipient unavailable")
        assert scroll["up"].endswith(older) and scroll["off-bottom"].endswith(older), (scroll["up"], scroll["off-bottom"])
        assert scroll["page"].endswith(" rows " + notice(client) + " " + notice(test(1))), scroll["page"]
        assert " pos=4 max=4 lines=6 thumb=57 " in scroll["limit"] and scroll["limit"].endswith(
            " rows " + notice(test(4)) + " " + notice(test(5))), scroll["limit"]
        assert " pos=0 max=4 lines=6 " in scroll["drag"] and scroll["drag"].endswith(
            " rows " + notice(client) + " " + notice(test(1))), scroll["drag"]
        assert " pos=0 max=5 lines=7 " in scroll["top"], scroll["top"]
        assert " pos=5 max=5 lines=7 thumb=57 " in scroll["hold"] and scroll["hold"].endswith(
            " rows " + notice(test(5)) + " " + notice(test(6))), scroll["hold"]
        assert SCROLL in text, text[-4000:]
        for line in scroll.values():
            print(line, flush=True)
        print(SCROLL, flush=True)
        print(PASS, flush=True)
finally:
    for client in graphics:
        if client.poll() is None:
            client.terminate()
            client.wait(timeout=5)
    for p in peers:
        try:
            p.s.close()
        except Exception:
            pass
    if server and server.poll() is None:
        server.terminate()
        server.wait(timeout=8)
    for log in logs:
        log.close()
    # PQ-128: each container's log, before it is removed.
    for c in containers:
        container_logs({name: "postgres", name + "-redis": "redis"}[c], ["docker", "logs", "--timestamps", c])
    for container in reversed(containers):
        run("docker", "rm", "-f", container, good=False)
