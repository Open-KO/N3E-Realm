"""The field input replay (--play-smoke) against a disposable stack (PQ-129, PQ-239).

  N3E_GRAPHICAL=1 python tests/play_replay_live.py

`make live` runs this on the synthetic demo package (build/packages/demo, cooked
by `make assets` from games/demo; its reward policy is converted first, as
tests/ko_stack.py does, and two more players stand at the start so the client
sees the five entities the replay checks for). It starts its own Compose
project, makes the accounts and characters, and with N3E_GRAPHICAL=1 runs one
test client through --play-smoke: a right drag and release (the camera turns
-0.3 rad), a wheel step (distance 7 to 6.3), a click travel with the desktop's
focus loss, pointer leave and cursor motion injected mid travel (PQ-238), the
target key, and with a HUD a strike click (answered by an action result, or with
the package's melee by auto-attack on the target) and a chat line the server
confirms. The client renders offscreen under `make live` (PQ-121), where SDL has
no relative mouse mode; the right drag turns the camera through the test
client's offscreen fallback (client/render/viewer.cpp, PQ-129, D-193). Without
N3E_GRAPHICAL=1 only the stack, accounts and characters are checked. `make live-ko`'s camera_legacy_live runs the
same replay on the KO field package (tests/camera_legacy_live.py).
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from world_peer import Peer
from isolation import DISPOSABLE_COMPOSE, container_logs


def replay(package, out, client=True, bystanders=0):
    """Run the replay on `package` with a stack of its own; logs and the capture
    go to `out`. `bystanders` more players stand at the start while the client
    runs (the replay needs five entities in view). Returns the client's PLAY
    line, or None when `client` is false."""
    package = Path(package).resolve()
    manifest = json.loads((package / "recipe.json").read_text())["manifest"]
    project = "n3e-play-replay-" + uuid.uuid4().hex[:10]
    env = {
        **os.environ,
        "N3E_PORT": "0",
        "N3E_REALM": "test-" + project,
        "N3E_PACKAGE_PATH": str(package),
        "N3E_UID": str(os.getuid()),
        "N3E_GID": str(os.getgid()),
    }
    base = ["docker", "compose", *DISPOSABLE_COMPOSE, "-p", project]
    password = "test-only-" + uuid.uuid4().hex
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    standing = []

    def dc(*args, input=None):
        p = subprocess.run(base + list(args), env=env, input=input, text=True, capture_output=True, timeout=120)
        if p.returncode:
            raise RuntimeError(f"docker compose {' '.join(args)}: exit {p.returncode}\n{p.stdout[-1500:]}{p.stderr[-1500:]}")
        return p.stdout

    try:
        if "progression" in manifest:
            # A package with a reward policy needs it converted before the server
            # starts (as tests/ko_stack.py does for the Moradon packages).
            dc("up", "-d", "--wait", "postgres", "redis")
            dc("run", "--rm", "--no-deps", "migrate")
            dc("run", "--rm", "--no-deps", "-e", "N3E_TEST_PROGRESSION=disposable", "server", "convert-progression")
        dc("up", "-d", "--wait")
        port = int(dc("port", "server", "7777").strip().rsplit(":", 1)[1])
        dc("exec", "-T", "server", "n3e-server", "account-create", "replay", input=password + "\n")
        def peer(account):
            return Peer(port, account, password, content=(package / "release.sha256").read_text().strip(),
                        game=manifest["game_id"], protocol=manifest["protocol_version"])

        player = peer("replay")
        player.create("Replay")
        player.s.close()
        for i in range(bystanders):
            dc("exec", "-T", "server", "n3e-server", "account-create", f"stand{i}", input=password + "\n")
            stander = peer(f"stand{i}")
            stander.select(stander.create(f"Stander{i}"))
            standing.append(stander)
        if not client:
            return None
        log = out / "client.log"
        with log.open("w") as handle:
            subprocess.run(
                ["build/client/n3e-test-client", str(package), "--connect", f"localhost:{port}",
                 "--ca", "deploy/local/ca.pem", "--auto-login", "--play-smoke", "7",
                 "--capture", str(out / "client.ppm")],
                env={**os.environ, "N3E_TEST_ACCOUNT": "replay", "N3E_TEST_PASSWORD": password},
                stdout=handle, stderr=subprocess.STDOUT, check=True, timeout=30)
        text = log.read_text()
        played = [line for line in text.splitlines() if line.startswith("PLAY orbit=")]
        assert played, text
        return played[-1]
    finally:
        # The standing players' logout can fail exactly when a kept log matters (a
        # server that died or dropped them), so it never skips the teardown.
        failed = []
        try:
            for stander in standing:
                try:
                    stander.logout()
                except Exception as error:  # noqa: BLE001 - reported, then raised below
                    failed.append(repr(error))
                    print("stander logout failed:", repr(error), flush=True)
                    stander.s.close()
        finally:
            # PQ-128: every service's log, before the stack is removed.
            container_logs("compose", [*base, "logs", "--no-color", "--timestamps"], env=env)
            dc("down", "-v", "--remove-orphans")
        # A logout failure on an otherwise passing run fails it; during another
        # failure that failure is the one raised.
        if failed and sys.exc_info()[0] is None:
            raise RuntimeError(f"standing players' logout failed: {failed}")


if __name__ == "__main__":
    graphical = os.environ.get("N3E_GRAPHICAL") == "1"
    # The demo shows the client two NPCs at the start; two standing players make
    # the five entities the replay checks for.
    played = replay("build/packages/demo", "build/play-replay/demo", client=graphical, bystanders=2)
    if graphical:
        print("PASS demo package right drag/release, zoom, click travel, HUD/chat and target replay:", played)
    else:
        print("PASS demo package replay stack, account and character (no client: N3E_GRAPHICAL unset)")
