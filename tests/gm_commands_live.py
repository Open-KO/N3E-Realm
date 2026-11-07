"""In-game GM commands: the `+` command path and `+give_item` (RQ-228, RQ-213;
specs/03-admin-api.md "In-game GM commands", acceptance test 12).

Starts the native server against a disposable Postgres and Redis with the original
item fixture of tests/inventory_live.py (a 12-slot bag; a practice blade that does
not stack and a practice potion that stacks to 20). Two TLS peers stand at the
spawn point: the game master and the player Aria. Checked: a `+` line from a
character without a GM capability reaches nearby players as chat; from a holder it
is never relayed. A command without its own capability answers "You may not use
..." with no audit row and no event; with it, the item lands in Aria's bag through
her own session (an unrequested BagResult), with one admin_audit row (outcome
gm_give_item, the bag before and after), the gm.command event, the log line and the
issuer's Chat{notice: 3}. Each refusal answers its line and changes nothing; a give
to a character out of the world is in its bag at its next entry; a full bag
refuses with nothing changed; a muted holder's command is dropped unread; a
revoked capability refuses the next command, and
with no GM capability left the `+` line is chat again.
"""
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from readiness import free_ports, wait_postgres
from isolation import DISPOSABLE_POSTGRES, container_logs
from world_peer import Peer, blob, first, fields
from inventory_live import prepare

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
server_binary = str(Path(os.environ.get("N3E_TEST_SERVER", "target/debug/n3e-server")).resolve())
package = prepare()
identity = (package / "release.sha256").read_text().strip()
name = "n3e-gm-" + uuid.uuid4().hex[:10]
realm = f"test-{name}"
out = ROOT / "build/live/gm-commands"
out.mkdir(parents=True, exist_ok=True)
password = "test-only-" + uuid.uuid4().hex
PROTOCOL = 8


def run(*cmd, env=None, good=True, stdin=None):
    p = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120, input=stdin)
    assert not good or p.returncode == 0, (cmd, p.returncode, p.stdout, p.stderr)
    return p


def events():
    """[(type, data)] of realm:events, oldest first."""
    raw = run("docker", "exec", name + "-redis", "redis-cli", "--json", "XRANGE", "realm:events", "-", "+").stdout
    found = []
    for _, values in json.loads(raw or "[]"):
        f = dict(zip(values[::2], values[1::2]))
        found.append((f["type"], json.loads(f["data"])))
    return found


def sql(q):
    return run("docker", "exec", name, "psql", "-U", "n3e", "-d", "n3e", "-Atc", q).stdout.strip()


def frames(peer, seconds, tags=(11, 33)):
    """The frames of `tags` that reach `peer` within `seconds`."""
    got = []
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            tag, data = peer.receive()
        except TimeoutError:
            continue
        if tag in tags:
            got.append((tag, data))
    return got


def chats(got):
    """(text, notice) of the Chat frames among `got`."""
    return [(first(d, 1, b"").decode(), first(d, 6)) for t, d in got if t == 11]


def bags(got):
    """The unrequested BagResults among `got`: their states."""
    return [fields(first(d, 3)) for t, d in got if t == 33 and not first(d, 1, b"")]


def call(port, method, path, token, body=None):
    """(status, parsed JSON or None) of one admin API request."""
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=5) as r:
            text = r.read()
            return r.status, (json.loads(text) if text else None)
    except urllib.error.HTTPError as e:
        text = e.read()
        e.close()
        return e.code, (json.loads(text) if text else None)


def records(state, item):
    return [fields(s) for s in state.get(5, []) if first(fields(s), 2, b"").decode() == item]


containers = []
server = None
peers = []
try:
    for suffix, image, cp, extra in [
        ("", "postgres:17.4-bookworm@sha256:304ab813518754228f9f792f79d6da36359b82d8ecf418096c636725f8c930ad", 5432,
         ["-e", "POSTGRES_USER=n3e", "-e", "POSTGRES_PASSWORD=test-only", "-e", "POSTGRES_DB=n3e", *DISPOSABLE_POSTGRES]),
        ("-redis", "redis:7.4.2-bookworm@sha256:fbdbaea47b9ae4ecc2082ecdb4e1cea81e32176ffb1dcf643d422ad07427e5d9", 6379, []),
    ]:
        run("docker", "run", "--rm", "-d", "--name", name + suffix, *extra, "-p", f"127.0.0.1::{cp}", image)
        containers.append(name + suffix)
    pg = wait_postgres(name)
    redis = run("docker", "port", name + "-redis", "6379").stdout.split()[0]
    listen, health, admin = free_ports(3)
    env = dict(os.environ, DATABASE_URL=f"host=127.0.0.1 port={pg} user=n3e password=test-only dbname=n3e",
               REDIS_ADDRESS=redis, N3E_PACKAGE=str(package), N3E_REALM=realm,
               N3E_LISTEN=f"127.0.0.1:{listen}", N3E_HEALTH=f"127.0.0.1:{health}",
               N3E_ADMIN_LISTEN=f"127.0.0.1:{admin}", N3E_LEGACY_LOGIN="1")
    run(server_binary, "migrate", env=env)
    run(server_binary, "convert-progression", env={**env, "N3E_TEST_PROGRESSION": "disposable"})
    for account in ("gm", "player", "faraway"):
        run(server_binary, "account-create", account, env=env, stdin=password + "\n")
    log_path = out / "server.log"
    log = open(log_path, "w")
    server = subprocess.Popen([server_binary], env=env, stdout=log, stderr=log)
    for _ in range(600):
        assert server.poll() is None, log_path.read_text()
        try:
            if urllib.request.urlopen(f"http://127.0.0.1:{health}/ready", timeout=.2).status == 200:
                break
        except Exception:
            time.sleep(.1)
    else:
        raise AssertionError("server not ready")

    def connect(account, character=None, create=None):
        p = Peer(listen, account, password, content=identity, game="demo", protocol=PROTOCOL)
        peers.append(p)
        if create:
            character = p.create(create)
        assert p.select(character)[0] == 10
        p.pump(.15)
        return p, character

    def role(character, cap, grant=True):
        run(server_binary, "role", "grant" if grant else "revoke", "gm", str(character), realm, cap, env=env)

    def say(peer, text):
        peer.send(11, blob(1, text))

    # Faraway enters once (so its bag exists) and leaves; Newbie enters only at the end.
    far = Peer(listen, "faraway", password, content=identity, game="demo", protocol=PROTOCOL)
    peers.append(far)
    far_id = far.create("Faraway")
    newbie_id = far.create("Newbie")
    assert far.select(far_id)[0] == 10
    far.send(32)
    far_bag = fields(first(far.until(33)[1], 3))
    assert len(records(far_bag, "demo:item/blade")) == 1, far_bag
    far.logout()
    gm, gm_id = connect("gm", create="Gamemaster")
    aria, aria_id = connect("player", create="Aria")

    def line(text, wait=1.2):
        """The game master says `text`; (what it receives, what Aria receives)."""
        say(gm, text)
        got_gm, got_aria = frames(gm, wait), frames(aria, .3)
        return got_gm, got_aria

    def answer(text):
        """The game master's command `text`: its one notice-3 line; Aria sees no chat."""
        got_gm, got_aria = line(text)
        replies = [t for t, n in chats(got_gm) if n == 3]
        assert len(replies) == 1 and not [c for c in chats(got_gm) if c[1] != 3], (text, chats(got_gm))
        assert not chats(got_aria), (text, "relayed", chats(got_aria))
        return replies[0], got_aria

    def audits():
        return int(sql(f"SELECT count(*) FROM admin_audit WHERE realm='{realm}' AND outcome='gm_give_item'"))

    # 1. Without any GM capability a `+` line is ordinary chat.
    got_gm, got_aria = line("+give_item Aria item/potion 5")
    assert ("+give_item Aria item/potion 5", 0) in chats(got_aria), chats(got_aria)
    assert not bags(got_aria) and audits() == 0
    print("PASS a + line from a character without a GM capability reaches nearby players as chat")

    # 2. A holder without gm.item: never relayed; refused with no audit row.
    role(gm_id, "gm.moderate")
    time.sleep(.8)  # the next authority read (500 ms lease)
    reply, _ = answer("+give_item Aria item/potion 5")
    assert reply == "You may not use +give_item.", reply
    assert audits() == 0
    reply, _ = answer("+hello there")
    assert reply == "Unknown command +hello.", reply
    print("PASS a holder's + line is never relayed; without gm.item: 'You may not use +give_item.', no audit row; "
          "an unknown verb answered")

    # 3. With gm.item the potion reaches Aria's bag through her own session.
    role(gm_id, "gm.item")
    reply, got_aria = answer("+give_item Aria item/potion 5")
    assert reply == "Gave Aria 5 x Practice potion.", reply
    got_aria += frames(aria, 1)
    states = bags(got_aria)
    assert states, ("no bag to Aria", got_aria)
    potions = records(states[-1], "demo:item/potion")
    assert sorted(first(p, 3) for p in potions) == [5, 5], potions  # the starting stack and a new record
    revision = first(states[-1], 1)
    row = sql(f"SELECT character_id||'|'||target||'|'||outcome||'|'||(before_state<>after_state)::text||'|'||reason||'|'||"
              f"(request LIKE 'gm-%')::text FROM admin_audit WHERE realm='{realm}' AND outcome='gm_give_item'")
    assert row == f"{gm_id}|character:{aria_id}|gm_give_item|true|+give_item Aria item/potion 5|true", row
    print("PASS +give_item to a character in the world: in its bag without leaving (revision", revision,
          "); one admin_audit row gm_give_item; the issuer's notice-3 line")

    # 4. Refusals: one line each, nothing changed.
    for text, expected in [
        ("+give_item Aria", "Usage: +give_item NAME ITEM [COUNT]"),
        ("+give_item Aria item/potion five", "Usage: +give_item NAME ITEM [COUNT]"),
        ("+give_item Nobody item/potion", "No character named Nobody."),
        ("+give_item Aria item/nothing", "No item item/nothing."),
        ("+give_item Aria demo:item/token", "No item demo:item/token."),
        ("+give_item aria item/potion 21", "COUNT for Practice potion is 1 to 20."),
        ("+give_item Aria item/blade 2", "COUNT for Practice blade is 1 to 1."),
    ]:
        reply, got_aria = answer(text)
        assert reply == expected, (text, reply)
        assert not bags(got_aria), (text, got_aria)
    assert audits() == 1
    print("PASS refusals: usage, unknown name, unknown item, the reward token, a count past the stack limit; "
          "each one line, nothing changed")

    # A muted holder's lines are dropped before they are read, commands included,
    # as KO drops a muted sender first (004989a8); the unmute restores them.
    mod = run(server_binary, "admin", "mint", "--name", "mod", "--perm", "account.mute", env=env).stdout.strip()
    gm_account = int(sql(f"SELECT account_id FROM characters WHERE id={gm_id}"))
    assert call(admin, "POST", f"/v1/accounts/{gm_account}/mute", mod, {"reason": "test", "until": None})[0] == 200
    say(gm, "+give_item Aria item/potion")
    tag, data = gm.until(4, seconds=3)
    assert (first(data, 1), first(data, 3)) == (7, 11), data
    got_gm, got_aria = frames(gm, 1.2), frames(aria, .3)
    assert not chats(got_gm) and not chats(got_aria) and not bags(got_aria) and audits() == 1, (
        chats(got_gm), chats(got_aria))
    assert call(admin, "POST", f"/v1/accounts/{gm_account}/unmute", mod, {})[0] == 200
    print("PASS a muted holder's command is dropped unread (the mute line, no answer, nothing given); "
          "the unmute restores it")

    # 5. A character out of the world gets it at its next entry.
    reply, _ = answer("+give_item faraway demo:item/blade")
    assert reply == "Gave Faraway 1 x Practice blade.", reply
    reply, _ = answer("+give_item Newbie item/potion 3")
    assert reply == "Gave Newbie 3 x Practice potion.", reply
    assert audits() == 3

    # 6. A full bag refuses with nothing changed.
    frames(aria, .5)
    aria.send(32)
    free = sum(1 for s in fields(first(aria.until(33)[1], 3))[5] if not first(fields(s), 1))
    assert 0 < free < 12, free
    for n in range(free):
        reply, _ = answer("+give_item Aria item/blade")
        assert reply == "Gave Aria 1 x Practice blade.", (n, reply)
    frames(aria, .5)
    aria.send(32)
    full = fields(first(aria.until(33)[1], 3))
    assert all(first(fields(s), 1) for s in full[5]) and len(full[5]) == 12, full
    reply, got_aria = answer("+give_item Aria item/potion")
    assert reply == "Aria's bag is full.", reply
    aria.send(32)
    after = fields(first(aria.until(33)[1], 3))
    assert after == full and audits() == 3 + free, (after == full, audits())
    print("PASS a full bag refuses with nothing changed (bag revision", first(after, 1), ", no audit row)")

    # 7. Revoked: the next command is refused; with no GM capability left, chat again.
    role(gm_id, "gm.item", grant=False)
    reply, _ = answer("+give_item Aria item/potion")
    assert reply == "You may not use +give_item.", reply
    role(gm_id, "gm.moderate", grant=False)
    time.sleep(.8)
    got_gm, got_aria = line("+give_item Aria item/potion")
    assert ("+give_item Aria item/potion", 0) in chats(got_aria) and not [c for c in chats(got_gm) if c[1] == 3], \
        (chats(got_gm), chats(got_aria))
    assert audits() == 3 + free
    print("PASS a revoked gm.item refuses the next command; with no GM capability the + line is chat again")

    far, _ = connect("faraway", far_id)
    far.send(32)
    far_bag = fields(first(far.until(33)[1], 3))
    assert len(records(far_bag, "demo:item/blade")) == 2, far_bag
    far.logout()
    newbie, _ = connect("faraway", newbie_id)
    newbie.send(32)
    newbie_bag = fields(first(newbie.until(33)[1], 3))
    assert 3 in [first(r, 3) for r in records(newbie_bag, "demo:item/potion")], newbie_bag
    print("PASS +give_item to a character out of the world: in its bag at its next entry (and at a first entry)")

    # 8. Events and log lines.
    gm_events = [d for t, d in events() if t == "gm.command"]
    assert [e["result"] for e in gm_events] == (
        ["given"] + ["usage", "usage", "no_character", "no_item", "no_item", "bad_count", "bad_count"]
        + ["given"] * (2 + free) + ["bag_full"]), [e["result"] for e in gm_events]
    assert gm_events[0] == {"character_id": gm_id, "character": "Gamemaster", "account_id": gm_events[0]["account_id"],
                            "verb": "give_item", "target": "Aria", "result": "given",
                            "detail": "Gave Aria 5 x Practice potion."}, gm_events[0]
    assert gm_events[3]["target"] == "" and gm_events[4]["target"] == "Aria", gm_events[3:5]
    text = log_path.read_text()
    assert text.count("gm by=Gamemaster verb=give_item target=- result=denied") == 2, text[-3000:]
    assert f"gm by=Gamemaster verb=give_item target=character:{aria_id} result=given" in text
    assert "gm by=Gamemaster verb=unknown target=- result=unknown" in text
    assert server.poll() is None and "panicked" not in text
    print("PASS gm.command for each command past its capability check (none for a refused capability or an "
          "unknown verb); log lines 'gm by=... verb=... target=... result=...'")
    print("GM_COMMANDS_OK")
finally:
    for p in peers:
        try:
            p.s.close()
        except Exception:
            pass
    if server is not None and server.poll() is None:
        server.terminate()
        try:
            server.wait(10)
        except subprocess.TimeoutExpired:
            server.kill()
    for c in containers:
        container_logs(c, ["docker", "logs", "--timestamps", c])
        run("docker", "rm", "-f", c, good=False)
