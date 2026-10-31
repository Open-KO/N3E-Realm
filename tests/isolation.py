"""Isolation for disposable live suites that run at the same time (PQ-114).

tests/live.py runs several suites at once. Two things the suites share would
otherwise race, and both helpers here behave exactly as before when their
environment variables are absent (a suite started by hand, or `make test`).

Ports. `free_ports` used to bind port 0 and release it, so the kernel picked
from the ephemeral range (32768-60999 here). Docker picks published ports and the
kernel picks client source ports from that same range, so a released port could
be taken by another suite's container or connection before the server bound it.
live.py gives each concurrent slot its own range below the ephemeral range
(N3E_TEST_PORTS=lo-hi) and a cursor file (N3E_TEST_PORT_STATE). Nothing else
allocates from that range automatically, slots never overlap, and the cursor,
advanced under a file lock, means successive calls in one suite, including from
child processes, never return a port twice before the range wraps.

Prepared packages. The feature fixtures cook a chain of packages
(build/ko-completion/items -> commerce -> ... -> item-drops): each `prepare`
re-cooks every ancestor, and assetc replaces a package directory by removing and
recopying it. A suite cooking a chain while another suite's server reads the same
package would see a missing or half-copied directory. With N3E_LIVE_CACHE set,
`once_per_run` runs each distinct prepare call (same function, same arguments)
once per live run under one file lock, records the result, and returns the
record to every later caller. A cooked package is then never rewritten while a
suite uses it. The same prepare called with other arguments that returns the
same directory would still overwrite it (a variant flag a directory name does not
reflect), so that is refused.

Container logs (PQ-128). A suite's server, client and database logs are files it
opens itself, and tests/live.py keeps those of a failed suite (the audit hook in
tests/live_reads lists them). What its containers printed is gone once it
removes them, so `container_logs` saves `docker logs NAME` or `docker compose
... logs` output before teardown into the suite's log directory: N3E_LIVE_LOGS,
which live.py gives each suite (emptied when it starts, kept whole when it
fails), or build/live/logs/<script>/ when the suite is run by hand.

Disposable Postgres (PQ-205, D-155). Every suite's Postgres shares the host's
disk with the others, and one cluster's fsync waits on everyone's: under the
4-job load commits took up to 1.7 s, past what a realm's 2 s admission leaves a
lease renewal (400 ms between renewals, D-142), so realms exited or closed their
sessions. A suite starts its clusters with DISPOSABLE_POSTGRES (`docker run`) or
DISPOSABLE_COMPOSE (Compose): initdb writes `fsync = off` into the cluster's
postgresql.conf and skips its own sync, so a commit still writes its WAL to the
kernel before it returns but never waits for the disk. Nothing a suite can do
(stop, restart or SIGKILL Postgres, remove its container) loses a committed
transaction; only a host crash could, and the cluster is thrown away. compose.yaml
and deploy/ keep Postgres's defaults. Under `make live` a command that would
create a Postgres cluster without them is refused and fails the run (PQ-207,
tests/disposable.py).

Test networks (PQ-457, D-229). A Compose project used to get its own
<project>_default bridge, created with an IPv4 address and removed again at
`down`, about one per Compose suite per run; with a veth per container, the host's
network manager and browsers saw the interfaces change all through a run (a browser
aborted requests with ERR_NETWORK_CHANGED). tests/live.py now gives each suite it
runs a test network from a fixed pool (n3e-test-net-0, -1, ...): `claim_network`
takes the lowest number no runner on the host holds (a flock under
/tmp/n3e-test-networks, so `make live` in another worktree or beside `make
live-ko` never shares one) and no process of the last suite on it still runs in
(the suite's session, recorded in the lock file, so a suite that outlives its
runner keeps its network), creates the network only the first time that number
is ever needed, and removes whatever an earlier holder left on it, saving those
containers' logs first. `network_env`
hands the suite N3E_TEST_NETWORK and N3E_TEST_NETWORK_EXTERNAL, and
DISPOSABLE_COMPOSE (tests/compose-disposable.yaml) makes that network the
project's external default network, so `up` creates and `down` removes no
bridge. The stacks find their services by the bare names postgres and redis, and
Docker's DNS on a shared network answers a name with every container that has
it, so one network holds one suite's stack at a time; no suite runs two Compose
stacks at once. The runner sweeps the network again when the suite ends and fails
a suite that left containers on it. Without the variables (a suite run by hand)
the project gets its own <project>_default network as before. Plain `docker run`
containers stay on Docker's permanent docker0 bridge: they publish ports to the
host and use no service names, and a veth per container is made on any bridge.
"""
import fcntl
import functools
import hashlib
import inspect
import os
import pickle
import re
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# `docker run` and `docker compose` options for a disposable test cluster (module
# docstring); tests/disposable.py owns them and the check that make live uses them.
from disposable import DISPOSABLE_COMPOSE, DISPOSABLE_POSTGRES  # noqa: E402,F401


def logs_dir():
    """The directory this suite's container logs go to (see the module docstring)."""
    named = os.environ.get("N3E_LIVE_LOGS")
    out = Path(named) if named else ROOT / "build/live/logs" / Path(sys.argv[0] or "manual").stem
    out.mkdir(parents=True, exist_ok=True)
    return out


def container_logs(label, command, env=None, directory=None):
    """Save what `command` prints (["docker", "logs", NAME] or a Compose base
    command plus ["logs", "--no-color"]) to logs_dir()/<label>.log, or to
    `directory`. Called in a suite's teardown before the containers are removed;
    never raises, so it cannot hide the suite's own failure or skip the teardown
    after it."""
    label = re.sub(r"[^\w.-]", "_", label)
    try:
        p = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, errors="replace",
                           timeout=60)
        text = f"$ {' '.join(command)}  (exit {p.returncode})\n{p.stdout}{p.stderr}"
    except (OSError, subprocess.SubprocessError) as error:
        text = f"$ {' '.join(command)}\ncontainer_logs: {error!r}\n"
    try:
        out = Path(directory) if directory else logs_dir()
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{label}.log").write_text(text)
    except OSError:
        pass


def free_ports(count):
    """`count` distinct free loopback ports. All sockets stay bound until every
    port is chosen, so two calls in a row cannot hand out the same port."""
    spec = os.environ.get("N3E_TEST_PORTS")
    if not spec:
        sockets = [socket.socket() for _ in range(count)]
        try:
            for s in sockets:
                s.bind(("127.0.0.1", 0))
            return [s.getsockname()[1] for s in sockets]
        finally:
            for s in sockets:
                s.close()
    lo, hi = map(int, spec.split("-"))
    span = hi - lo + 1
    with open(os.environ["N3E_TEST_PORT_STATE"], "a+") as state:
        fcntl.flock(state, fcntl.LOCK_EX)
        state.seek(0)
        text = state.read().strip()
        cursor = int(text) if text else lo
        chosen, sockets = [], []
        try:
            for step in range(span):
                port = lo + (cursor - lo + step) % span
                s = socket.socket()
                try:
                    s.bind(("127.0.0.1", port))
                except OSError:
                    s.close()
                    continue
                sockets.append(s)
                chosen.append(port)
                if len(chosen) == count:
                    break
            if len(chosen) < count:
                raise RuntimeError(f"free_ports: only {len(chosen)} of {count} free in {spec}")
            state.seek(0)
            state.truncate()
            state.write(str(lo + (chosen[-1] + 1 - lo) % span))
            return chosen
        finally:
            for s in sockets:
                s.close()


_held = 0


@contextmanager
def _prepare_lock(cache):
    """One lock for every prepare in the run. Prepares call their ancestors, so
    the lock is reentrant within a process; across processes it is a flock."""
    global _held
    if _held:
        _held += 1
        try:
            yield
        finally:
            _held -= 1
        return
    cache.mkdir(parents=True, exist_ok=True)
    with open(cache / ".lock", "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        _held = 1
        try:
            yield
        finally:
            _held = 0


def _outputs(result):
    items = result if isinstance(result, (list, tuple)) else [result]
    return sorted(str(Path(p).resolve()) for p in items if isinstance(p, (str, Path)))


def once_per_run(fn):
    """Run `fn` once per live run for each distinct set of arguments."""
    signature = inspect.signature(fn)
    where = f"{Path(inspect.getsourcefile(fn)).resolve().relative_to(ROOT)}:{fn.__qualname__}"

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        cache = os.environ.get("N3E_LIVE_CACHE")
        if not cache:
            return fn(*args, **kwargs)
        cache = Path(cache)
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        arguments = sorted((k, str(v) if isinstance(v, Path) else v) for k, v in bound.arguments.items())
        key = f"{where}{arguments!r}"
        record = cache / (hashlib.sha256(key.encode()).hexdigest()[:24] + ".pickle")
        with _prepare_lock(cache):
            if record.exists():
                return pickle.loads(record.read_bytes())["result"]
            result = fn(*args, **kwargs)
            outputs = _outputs(result)
            for other in cache.glob("*.pickle"):
                seen = pickle.loads(other.read_bytes())
                # A prepare may return an ancestor's directory; only one function
                # called with other arguments rewrites the same directory.
                shared = set(outputs) & set(seen["outputs"]) if seen["where"] == where else set()
                if shared:
                    raise AssertionError(f"two prepare variants write {sorted(shared)}: {key} and {seen['key']}")
            partial = record.with_suffix(".partial")
            partial.write_bytes(pickle.dumps({"key": key, "where": where, "outputs": outputs, "result": result}))
            partial.replace(record)
            return result

    return wrapper


# Test networks (PQ-457): see the module docstring.
NETWORK_PREFIX = "n3e-test-net-"
NETWORK_LABEL = "n3e.test-network"
# Host-wide, not per checkout: two runners (make live in two worktrees, or beside
# make live-ko) must never hold the same network.
NETWORK_LOCKS = Path("/tmp/n3e-test-networks")


def _docker(*args, timeout=120):
    return subprocess.run(["docker", *args], capture_output=True, text=True, errors="replace", timeout=timeout)


def network_env(name):
    """What a suite's processes get so that DISPOSABLE_COMPOSE puts the stack on
    `name` (tests/compose-disposable.yaml); None removes both (a hand run)."""
    return {"N3E_TEST_NETWORK": name, "N3E_TEST_NETWORK_EXTERNAL": "true" if name else None}


def ensure_network(name):
    """Create test network `name` unless it exists; True when this call created it.
    A network of that name that is not a test network is refused."""
    p = _docker("network", "inspect", "--format", '{{.Driver}} {{index .Labels "%s"}}' % NETWORK_LABEL, name)
    if p.returncode == 0:
        if p.stdout.split() != ["bridge", "1"]:
            raise RuntimeError(f"network {name} exists but is not an n3e test network ({p.stdout.strip()!r})")
        return False
    p = _docker("network", "create", "--driver", "bridge", "--label", f"{NETWORK_LABEL}=1", name)
    if p.returncode:
        raise RuntimeError(f"docker network create {name}: exit {p.returncode}: {p.stderr.strip()[-400:]}")
    return True


def sweep_network(name, logs=None):
    """Remove every container attached to `name` (running or not) and the volumes
    of the Compose projects they belong to, first saving each container's output
    (`docker logs`) to `logs`/left-<container>.log (PQ-128: the suite's own
    teardown, which would have saved it, did not run). Only the holder of the
    network's claim calls it, so what it finds is a stack an earlier holder left.
    Returns the removed containers' names; raises if any is still attached."""
    ids = _docker("ps", "-aq", "--no-trunc", "--filter", f"network={name}").stdout.split()
    if not ids:
        return []
    shown = _docker("inspect", "--format",
                    '{{.Name}} {{index .Config.Labels "com.docker.compose.project"}}', *ids).stdout.split("\n")
    names, projects = [], set()
    for line in (l.split() for l in shown if l.strip()):
        names.append(line[0].lstrip("/"))
        projects.update(line[1:2])
    if logs:
        for container in names:
            container_logs(f"left-{container}", ["docker", "logs", "--timestamps", container], directory=logs)
    _docker("rm", "-f", "-v", *ids, timeout=300)
    for project in sorted(projects):
        volumes = _docker("volume", "ls", "-q", "--filter", f"label=com.docker.compose.project={project}").stdout.split()
        if volumes:
            _docker("volume", "rm", "-f", *volumes)
    left = _docker("ps", "-aq", "--filter", f"network={name}").stdout.split()
    if left:
        raise RuntimeError(f"containers still on {name} after the sweep: {' '.join(left)}")
    return sorted(names)


def session_alive(sid):
    """Whether any process on the host is still in session `sid`."""
    for stat in Path("/proc").glob("[0-9]*/stat"):
        try:
            fields = stat.read_text().rsplit(")", 1)[1].split()
        except (OSError, IndexError):
            continue
        if len(fields) > 3 and fields[3] == str(sid):
            return True
    return False


class TestNetwork:
    """A claimed test network: `name`, whether the claim created it, what the
    claim's sweep removed (`swept`) and where it saved their logs (`swept_logs`)."""

    def __init__(self, name, created, swept, swept_logs, handle):
        self.name, self.created, self.swept, self.swept_logs = name, created, swept, swept_logs
        self._handle = handle

    def hold(self, sid):
        """Record session `sid` (the suite, started as a session leader) in the
        network's lock file: until every process of that session has exited, no
        claim takes the network, even after this claim's lock is released."""
        self._handle.seek(0)
        self._handle.truncate()
        self._handle.write(str(sid))
        self._handle.flush()


@contextmanager
def claim_network(logs=None):
    """Hold the lowest-numbered test network no other claim holds, for one suite.

    A network is held while its host-wide lock is (by the claiming runner) and,
    after that, while any process remains of the session last recorded with
    TestNetwork.hold (the suite and every process it started), so a suite that
    outlives its runner (SIGKILL, or a teardown still running when an interrupted
    runner exits) keeps its network. The claim creates the network if it does not
    exist yet (only the first time that number is ever needed) and removes whatever
    an earlier holder left on it, saving those containers' logs under
    `logs`/<time>-<network>/, so the suite starts on an empty network. The lock is
    released when the block ends; the caller sweeps again before that
    (sweep_network) to find what the suite itself left."""
    NETWORK_LOCKS.mkdir(parents=True, exist_ok=True)
    index = 0
    while True:
        handle = open(NETWORK_LOCKS / f"{NETWORK_PREFIX}{index}.lock", "a+")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            handle.seek(0)
            recorded = handle.read().strip()
            if not (recorded.isdigit() and session_alive(int(recorded))):
                break
        except BlockingIOError:
            pass
        handle.close()
        index += 1
    try:
        name = f"{NETWORK_PREFIX}{index}"
        created = ensure_network(name)
        where = Path(logs) / f"{time.strftime('%Y%m%d-%H%M%S')}-{name}" if logs else None
        swept = sweep_network(name, where)
        yield TestNetwork(name, created, swept, where if swept else None, handle)
    finally:
        handle.close()
