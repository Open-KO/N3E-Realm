"""Disposable test Postgres: the options and the check that `make live` uses them
(PQ-205, PQ-207, D-155).

Every live-tier suite's Postgres shares the host's disk, and under the 4-job load
a commit's fsync waited up to 1.7 s, past what a realm's admission leaves a lease
renewal (D-142), so realms exited or closed sessions. A disposable cluster is
created with initdb's `--no-sync --set fsync=off`: DISPOSABLE_POSTGRES for `docker
run`, DISPOSABLE_COMPOSE (compose.yaml plus tests/compose-disposable.yaml) for
Compose. tests/isolation.py re-exports both for the suites.

problem(argv) is the check (PQ-207). tests/live_reads/sitecustomize.py loads this
file in every Python process `make live` starts and calls it for each command the
process starts (subprocess, os.exec*, os.posix_spawn, os.system). It names, and
the hook refuses, a command that would create a Postgres cluster without the
options:

- `docker run` or `docker create` (also `docker container run|create`) whose
  arguments name a postgres image (`postgres`, `postgres:<tag>`,
  `<registry>/postgres@<digest>`, ...) without DISPOSABLE_POSTGRES, in that
  order, before that image argument;
- `docker compose` (or `docker-compose`) `up`, `create` or `run` without
  DISPOSABLE_COMPOSE as its first options, in that order: a Compose project in
  this repository starts compose.yaml's Postgres, and these are the commands that
  create its container. Other Compose commands (exec, logs, port, down, stop,
  start, restart, build ...) never run initdb and pass.

Each simple command is read from its first `docker`, `docker-compose` or shell
token: what comes before is a wrapper (`env -u X`, `A=B`, `timeout 60`, `exec`,
`nice` ...), so a wrapped start is still checked. A shell's command line (the
argument after an option cluster holding `c`: `-c`, `-lc`, `-ec`) is split at
its operators and each command checked the same way. It fails closed: a
postgres-image argument it cannot tell from a container name or command argument
counts as an image (`docker run --name postgres redis` is refused), a Compose
`up` with files given another way (COMPOSE_FILE, `--file=`) is refused, and an
error while checking refuses the command. Not seen: commands Python processes do
not start (the native client and server start no containers), a command hidden
in one argument other than a shell's command line (`env -S "..."`, a script
file a shell runs), a shell variable holding the image or the command (`docker
run $IMG` in a shell's command line is read as the literal `$IMG`), a docker
binary under another name, and a start by a child process whose environment
drops PYTHONPATH or N3E_LIVE_DISPOSABLE (the hook is not loaded there, or does
not check).

`make live` and, since PQ-208, `make live-ko` (tests/live_ko.py) run the check.
"""
import os
import re
import shlex

# `docker run` options for a disposable test cluster.
DISPOSABLE_POSTGRES = ["-e", "POSTGRES_INITDB_ARGS=--no-sync --set fsync=off"]
# `docker compose` file options: compose.yaml with the same initdb options.
DISPOSABLE_COMPOSE = ["-f", "compose.yaml", "-f", "tests/compose-disposable.yaml"]

# An image reference whose repository's last component is `postgres`.
POSTGRES_IMAGE = re.compile(r"(?:[\w.-]+(?::\d+)?/)*postgres(?:[:@]\S*)?")
# docker's and docker compose's global options that take a separate value.
DOCKER_VALUE_OPTIONS = {"-c", "--context", "-H", "--host", "--config", "-l", "--log-level",
                        "--tlscacert", "--tlscert", "--tlskey"}
COMPOSE_VALUE_OPTIONS = {"-f", "--file", "-p", "--project-name", "--env-file", "--profile",
                         "--project-directory", "--ansi", "--progress", "--parallel"}
COMPOSE_CREATES = {"up", "create", "run"}
SHELLS = {"sh", "bash", "dash", "zsh"}
SHELL_OPERATORS = {";", "&&", "||", "|", "&", "(", ")", "\n"}
# A shell option cluster that makes the next argument the command line.
SHELL_C = re.compile(r"-[A-Za-z]*c[A-Za-z]*")


def _contains(seq, part):
    return any(seq[i:i + len(part)] == part for i in range(len(seq) - len(part) + 1))


def _subcommand(args, value_options):
    """(index, token) of the first argument that is neither an option nor an
    option's value, or (len(args), None)."""
    i = 0
    while i < len(args):
        a = args[i]
        if a in value_options:
            i += 2
        elif a.startswith("-"):
            i += 1
        else:
            return i, a
    return len(args), None


def _compose(args):
    i, sub = _subcommand(args, COMPOSE_VALUE_OPTIONS)
    if sub in COMPOSE_CREATES and args[:len(DISPOSABLE_COMPOSE)] != DISPOSABLE_COMPOSE:
        return (f"`docker compose {sub}` without tests/isolation.py DISPOSABLE_COMPOSE as its first "
                f"options ({' '.join(DISPOSABLE_COMPOSE)})")
    return None


def _command(argv):
    name = os.path.basename(argv[0]) if argv else ""
    if name == "docker-compose":
        return _compose(argv[1:])
    if name != "docker":
        return None
    i, sub = _subcommand(argv[1:], DOCKER_VALUE_OPTIONS)
    rest = argv[2 + i:]
    if sub == "compose":
        return _compose(rest)
    if sub == "container" and rest:
        sub, rest = rest[0], rest[1:]
    if sub not in ("run", "create"):
        return None
    at = next((n for n, a in enumerate(rest) if POSTGRES_IMAGE.fullmatch(a)), None)
    if at is None:
        return None
    image = rest[at]
    # The options go before the image; after it they are the container's command.
    if not _contains(rest[:at], DISPOSABLE_POSTGRES):
        return (f"`docker {sub}` of {image.split('@')[0]} without tests/isolation.py DISPOSABLE_POSTGRES "
                f"({' '.join(DISPOSABLE_POSTGRES)})")
    return None


def _shell(text):
    """Each simple command of a shell command line, split at its operators."""
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    commands, current = [], []
    for token in lexer:
        if token in SHELL_OPERATORS or set(token) <= set(";&|()"):
            commands.append(current)
            current = []
        else:
            current.append(token)
    return [c for c in commands + [current] if c]


def _simple(command, depth=0):
    """The problem with one simple command. Everything before its first `docker`,
    `docker-compose` or shell token is a wrapper (`env -u X`, `A=B`, `timeout 60`,
    `exec`, `nice`, ...); a shell's command line (the argument after any option
    cluster holding `c`: `-c`, `-lc`, `-ec`) is checked command by command."""
    for i, token in enumerate(command):
        name = os.path.basename(token)
        if name in ("docker", "docker-compose"):
            return _command(command[i:])
        if name in SHELLS:
            rest = command[i + 1:]
            at = next((n for n, a in enumerate(rest) if SHELL_C.fullmatch(a)), None)
            if at is None or at + 1 >= len(rest):
                return None
            if depth > 8:
                return "shell command lines nested too deep to check"
            for inner in _shell(rest[at + 1]):
                found = _simple(inner, depth + 1)
                if found:
                    return found
            return None
    return None


def problem(argv):
    """Why the command `argv` (a list, or a shell command line as a string) would
    start a non-disposable Postgres, or None. Any error while checking is itself
    a problem (fail closed)."""
    try:
        if isinstance(argv, os.PathLike):
            argv = [argv]
        if isinstance(argv, (str, bytes)):
            commands = _shell(os.fsdecode(argv))
        else:
            commands = [[os.fsdecode(a) for a in argv]]
        for command in commands:
            found = _simple(command)
            if found:
                return found
        return None
    except Exception as error:
        return f"unreadable command ({type(error).__name__}: {error})"
