"""Original/optional KO graphical death, ready prompt and E request through production input."""

import json, os, subprocess, sys, time, uuid
from pathlib import Path
from world_peer import Peer, first

sys.path.insert(0, str(Path("tools/assetc").resolve()))
import life_fixture, main

B = Path("build/ko-06")
B.mkdir(parents=True, exist_ok=True)
ko = "--ko" in sys.argv
life_fixture.cook(ko)
root = Path("build/ko-01/source-ko" if ko else "build/ko-01/source")
m = json.loads((root / "package.json").read_text())
m["gameplay"]["npc_health"] = 1500
(root / "package.json").write_text(json.dumps(m))
package = (B / ("graphics-ko" if ko else "graphics")).resolve()
main.cook(root, package)
project = "n3e-ko06-graphics-" + uuid.uuid4().hex[:8]
env = {
    **os.environ,
    "N3E_PORT": "0",
    "N3E_REALM": project,
    "N3E_PACKAGE_PATH": str(package),
    "N3E_UID": str(os.getuid()),
    "N3E_GID": str(os.getgid()),
}
base = ["docker", "compose", "-p", project]
password = "test-only-" + uuid.uuid4().hex
peers = []


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


try:
    dc("up", "--build", "-d", "--wait")
    port = int(dc("port", "server", "7777").strip().rsplit(":", 1)[1])
    for frame_ms in [33, 7]:
        name = "viewer" + str(frame_ms)
        dc(
            "exec",
            "-T",
            "server",
            "n3e-server",
            "account-create",
            name,
            stdin=password + "\n",
        )
        p = Peer(
            port,
            name,
            password,
            game=m["game_id"],
            protocol=3,
            content=(package / "release.sha256").read_text().strip(),
        )
        cid = p.create("Viewer" + str(frame_ms))
        if frame_ms == 7:
            p.select(cid)
            deadline = time.monotonic() + 15
            while first(p.entities[p.id], 7) > 0:
                assert time.monotonic() < deadline, "seed death deadline"
                p.move(-0.707, -0.707, mode=1)
                time.sleep(0.055)
                p.until(10)
            p.logout()
            print("PASS seeded committed death before graphical reconnect", flush=True)
        else:
            p.s.close()
        log = B / f"{package.name}-{frame_ms}.log"
        with log.open("w") as output:
            run = subprocess.run(
                [
                    "build/client/n3e-test-client",
                    str(package),
                    "--connect",
                    f"localhost:{port}",
                    "--ca",
                    "deploy/local/ca.pem",
                    "--auto-login",
                    "--life-smoke",
                    "18",
                    "--capture",
                    str(B / f"{package.name}-{frame_ms}.ppm"),
                ],
                env={
                    **env,
                    "N3E_TEST_ACCOUNT": name,
                    "N3E_TEST_PASSWORD": password,
                    "N3E_TEST_FRAME_MS": str(frame_ms),
                },
                stdout=output,
                stderr=subprocess.STDOUT,
                timeout=30,
            )
        assert run.returncode == 0, log.read_text()
        assert "LIFE requested replacement clears prediction" in log.read_text()
        print(
            f"PASS {package.name} {frame_ms}ms frame delay death cancels melee, persistent ready prompt, E respawn clears identity/prediction",
            flush=True,
        )
finally:
    (B / f"{package.name}-server.log").write_text(dc("logs", "--no-color", "server"))
    dc("down", "-v", "--remove-orphans")
