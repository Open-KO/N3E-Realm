"""Read audit and written-log record for tests/live.py (PQ-124, PQ-128).

tests/live.py puts this directory on PYTHONPATH for every process `make live`
starts, so Python imports this module at start-up in each of them.

Reads (PQ-124). When N3E_LIVE_READS names a directory, it records the repository
files the process opens (open(), io.open_code() and so module imports, through
the "open" audit event) and writes them at exit to N3E_LIVE_READS/<pid>.txt.
tests/live.py then fails the run on a tracked file that would not select the
gate's live tier.

Written logs (PQ-128). When N3E_LIVE_KEEP names a file (tests/live.py gives each
suite its own), each log the process opens for writing, a *.log or *.txt file
under build/, is appended to it as an absolute path the moment it is first
opened, so a suite that is later killed still has its logs listed. This is how a
suite reports the server, client and database logs it writes: tests/live.py
copies every listed file of a failed suite to build/live/failed/<run>/<suite>/
before the next run overwrites it. The runner's own read records
(N3E_LIVE_READS) and the per-suite container-log directory (N3E_LIVE_LOGS, kept
whole) are left out.

Disposable Postgres (PQ-207, D-155). When N3E_LIVE_DISPOSABLE is 1 (tests/live.py
gives it to every process `make live` and `make live-ko` start), it loads tests/disposable.py and
checks each command the process starts (the subprocess.Popen, os.exec,
os.posix_spawn and os.system audit events) with its problem(): a command that
would create a Postgres cluster without the fsync-off options (also behind a
wrapper such as `env -u X`, `timeout 60` or `sh -lc`; tests/disposable.py lists
what it cannot see) is refused with a RuntimeError before it runs, and named in
N3E_LIVE_READS/<pid>.undisposable, so tests/live.py fails the run with an
UNDISPOSABLE line even when a suite catches the error. If tests/disposable.py
cannot be loaded, or the check itself fails, the command is refused and recorded.

Limits: only Python processes are seen (the native client and server write to
files these processes open for them), and a process that ends without running
atexit (os._exit, SIGKILL) records no reads; its written logs are already listed.
"""
import os
import sys

_OUT = os.environ.get("N3E_LIVE_READS")
_KEEP = os.environ.get("N3E_LIVE_KEEP")
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) + os.sep

if _OUT or _KEEP:
    import atexit

    _seen = set()
    _written = set()
    _BUILD = _ROOT + "build" + os.sep
    _SKIP = tuple(os.path.abspath(d) + os.sep for d in (_OUT, os.environ.get("N3E_LIVE_LOGS")) if d)
    _KEEP_PATH = os.path.abspath(_KEEP) if _KEEP else None

    def _record_written(path):
        # The append below raises its own "open" event, which _hook ignores (the list
        # itself is never a log, and a path is recorded once). No lock or flag: a
        # flag shared by threads would hide other threads' reads from the audit.
        _written.add(path)
        try:
            fd = os.open(_KEEP, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
            try:
                os.write(fd, (path + "\n").encode(errors="surrogateescape"))
            finally:
                os.close(fd)
        except OSError:
            pass

    def _hook(event, args):
        if event != "open" or not args or isinstance(args[0], int):
            return
        try:
            path = os.path.abspath(os.fsdecode(args[0]))
        except (TypeError, ValueError, OSError):
            return
        if not path.startswith(_ROOT):
            return
        if _OUT:
            _seen.add(path)
        flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
        if (_KEEP and flags & os.O_ACCMODE != os.O_RDONLY and path.startswith(_BUILD)
                and path.endswith((".log", ".txt")) and not path.startswith(_SKIP)
                and path != _KEEP_PATH and path not in _written):
            _record_written(path)

    def _flush():
        if not _OUT or not _seen:
            return
        lines = sorted(_seen)
        try:
            with open(os.path.join(_OUT, f"{os.getpid()}.txt"), "a") as out:
                out.write("\n".join(lines) + "\n")
        except OSError:
            pass

    sys.addaudithook(_hook)
    atexit.register(_flush)


if os.environ.get("N3E_LIVE_DISPOSABLE") == "1":
    def _load_check():
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("_n3e_disposable", _ROOT + "tests/disposable.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module.problem
        except Exception as error:   # fail closed: refuse every command
            reason = f"tests/disposable.py did not load ({type(error).__name__}: {error})"
            return lambda argv: reason

    _problem = _load_check()
    _STARTS = {"subprocess.Popen": 1, "os.exec": 1, "os.posix_spawn": 1, "os.system": 0}

    def _refuse(event, args):
        at = _STARTS.get(event)
        if at is None or len(args) <= at:
            return
        try:
            reason = _problem(args[at])
        except Exception as error:   # fail closed, and still recorded below
            reason = f"check failed ({type(error).__name__}: {error})"
        if not reason:
            return
        script = sys.argv[0] if sys.argv and sys.argv[0] else "python"
        if _OUT:
            try:
                fd = os.open(os.path.join(_OUT, f"{os.getpid()}.undisposable"),
                             os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
                try:
                    os.write(fd, f"{script}: {reason}\n".encode(errors="replace"))
                finally:
                    os.close(fd)
            except OSError:
                pass
        raise RuntimeError(f"refused {reason} (PQ-207, D-155: make live and make live-ko start only disposable Postgres)")

    sys.addaudithook(_refuse)
