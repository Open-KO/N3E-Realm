"""Concurrency checks for tests/isolation.py (PQ-114, PQ-457), without Docker.

Real processes race here, as the suites do under tests/live.py: many children ask
one slot for ports at once, many children call one prepare at once, and many
children claim a test network at once (Docker stubbed out: only the claim's
host-wide lock is checked here; make live exercises the networks themselves).
"""
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation  # noqa: E402
from isolation import free_ports, once_per_run  # noqa: E402

HERE = Path(__file__).resolve()


@once_per_run
def cooked(out, variant="base", delay=0.0):
    """Stands in for a feature prepare: slow, counts its runs, returns a path."""
    with open(Path(out) / "runs.log", "a") as log:
        log.write(f"{variant}\n")
    time.sleep(delay)
    return Path(out) / variant


@once_per_run
def outer(out):
    return [cooked(out, "inner"), Path(out) / "outer"]


def child(mode, *rest):
    if mode == "ports":
        print(json.dumps(free_ports(int(rest[0]))))
    elif mode == "cook":
        print(json.dumps(str(cooked(rest[0], "base", 0.3))))
    elif mode == "claim":
        # Docker stubbed: the network always exists and nothing is left on it.
        isolation.NETWORK_LOCKS = Path(rest[0])
        isolation.ensure_network = lambda name: False
        isolation.sweep_network = lambda name, logs=None: []
        with isolation.claim_network() as network:
            if rest[2:] == ("orphan",):
                # As tests/live.py runs a suite: in its own session, recorded.
                suite = subprocess.Popen(["sleep", "600"], start_new_session=True)
                network.hold(suite.pid)
                print(json.dumps([network.name, suite.pid]), flush=True)
            else:
                print(json.dumps(network.name), flush=True)
            time.sleep(float(rest[1]))


def spawn(env, *args):
    return subprocess.Popen([sys.executable, str(HERE), "--child", *args], env={**os.environ, **env},
                            stdout=subprocess.PIPE, text=True)


def results(procs):
    out = []
    for p in procs:
        text, _ = p.communicate(timeout=60)
        assert p.returncode == 0, p.returncode
        out.append(json.loads(text))
    return out


def main():
    for key in ("N3E_TEST_PORTS", "N3E_TEST_PORT_STATE", "N3E_LIVE_CACHE"):
        os.environ.pop(key, None)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        # Unset: the kernel's choice, distinct within one call.
        ports = free_ports(4)
        assert len(set(ports)) == 4, ports

        # Twelve processes race for one slot: no port twice, all inside the range.
        slot = {"N3E_TEST_PORTS": "20400-20499", "N3E_TEST_PORT_STATE": str(td / "ports-0")}
        got = [p for r in results([spawn(slot, "ports", "3") for _ in range(12)]) for p in r]
        assert len(got) == 36 and len(set(got)) == 36, got
        assert all(20400 <= p <= 20499 for p in got), got
        # The cursor persists across processes: the next call continues after them.
        assert results([spawn(slot, "ports", "1")])[0][0] not in got

        # A port something else holds is skipped, not returned.
        (td / "ports-1").write_text("20500")
        with socket.socket() as busy:
            busy.bind(("127.0.0.1", 20500))
            other = {"N3E_TEST_PORTS": "20500-20504", "N3E_TEST_PORT_STATE": str(td / "ports-1")}
            assert results([spawn(other, "ports", "2")])[0] == [20501, 20502]
            # The cursor wraps; with every port bound the call fails instead of sharing.
            holds = []
            try:
                for port in (20501, 20502, 20503, 20504):
                    s = socket.socket()
                    s.bind(("127.0.0.1", port))
                    holds.append(s)
                failing = subprocess.Popen([sys.executable, str(HERE), "--child", "ports", "1"],
                                           env={**os.environ, **other}, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE, text=True)
                _, err = failing.communicate(timeout=60)
                assert "only 0 of 1 free" in err, err
                assert failing.returncode != 0
            finally:
                for s in holds:
                    s.close()

        # Unset cache: every call runs, as a suite started by hand expects.
        plain = td / "plain"
        plain.mkdir()
        cooked(plain)
        cooked(plain)
        assert (plain / "runs.log").read_text() == "base\nbase\n"

        # Eight processes call one prepare at once: it runs once, all get its result.
        os.environ["N3E_LIVE_CACHE"] = str(td / "cache")
        shared = td / "shared"
        shared.mkdir()
        got = results([spawn({}, "cook", str(shared)) for _ in range(8)])
        assert got == [str(shared / "base")] * 8, got
        assert (shared / "runs.log").read_text() == "base\n"
        # Defaults are part of the key, so spelling them out is the same call.
        assert cooked(shared, variant="base", delay=0.3) == shared / "base"
        assert (shared / "runs.log").read_text() == "base\n"
        # A nested prepare in the same process does not deadlock and is cached too.
        assert outer(shared) == [shared / "inner", shared / "outer"]
        assert outer(shared) == [shared / "inner", shared / "outer"]
        assert (shared / "runs.log").read_text() == "base\ninner\n"
        # Two different calls that would write one directory are refused.
        try:
            cooked(shared, "base", 0.1)
        except AssertionError as error:
            assert "two prepare variants" in str(error), error
        else:
            raise AssertionError("conflicting prepare variants were accepted")

        # PQ-457: eight processes claim test networks at once; each holds its own,
        # the lowest numbers, until it ends.
        locks = td / "networks"
        names = [isolation.NETWORK_PREFIX + str(i) for i in range(8)]
        got = results([spawn({}, "claim", str(locks), "3") for _ in range(8)])
        assert sorted(got) == sorted(names), got
        # A released network is claimed again; one whose holder was killed too.
        assert results([spawn({}, "claim", str(locks), "0")]) == [names[0]]
        holder = spawn({}, "claim", str(locks), "60")
        assert json.loads(holder.stdout.readline()) == names[0]
        assert results([spawn({}, "claim", str(locks), "0")]) == [names[1]]
        holder.send_signal(signal.SIGKILL)
        holder.wait(timeout=60)
        assert results([spawn({}, "claim", str(locks), "0")]) == [names[0]]
        # A suite that outlives its runner keeps the network until it exits.
        holder = spawn({}, "claim", str(locks), "60", "orphan")
        name, orphan = json.loads(holder.stdout.readline())
        assert name == names[0]
        holder.send_signal(signal.SIGKILL)
        holder.wait(timeout=60)
        assert isolation.session_alive(orphan)
        assert results([spawn({}, "claim", str(locks), "0")]) == [names[1]]
        os.kill(orphan, signal.SIGKILL)
        deadline = time.monotonic() + 30
        while isolation.session_alive(orphan) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert results([spawn({}, "claim", str(locks), "0")]) == [names[0]]
    print("PASS isolation: per-slot port ranges under 12-process races, busy/exhausted ports, "
          "once-per-run prepare under 8-process races, nesting, default keys and variant conflicts, "
          "test network claims under 8-process races, after a killed holder and while a killed holder's suite lives")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--child"]:
        child(*sys.argv[2:])
    else:
        main()
