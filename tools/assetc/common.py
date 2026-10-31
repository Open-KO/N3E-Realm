"""Bounded, deterministic package primitives. Original n3e implementation."""

import hashlib, json, math, pathlib, re, struct

MAX_FILE = 16 * 1024 * 1024
# A package's static world asset carries a map-sized atlas and vertex buffer, so
# it has its own larger bound. Everything else stays at 16 MiB.
MAX_WORLD_FILE = 32 * 1024 * 1024
# Most spawn points (N3G2/N3G3), reference NPC slots (N3N2/N3N3) and editing
# spawn targets one package carries: server/src/rules.rs MAX_SPAWNS (PQ-250).
MAX_SPAWNS = 2048


def read(p, limit=MAX_FILE):
    if p.stat().st_size > limit:
        raise ValueError("file exceeds %d MiB" % (limit // (1024 * 1024)))
    return p.read_bytes()


def safe(root, name):
    if (
        not isinstance(name, str)
        or not re.fullmatch(r"[A-Za-z0-9_./-]{1,200}", name)
        or ".." in pathlib.PurePosixPath(name).parts
        or name.startswith("/")
    ):
        raise ValueError("unsafe dependency path")
    p = (root / name).resolve()
    if not p.is_relative_to(root.resolve()):
        raise ValueError("dependency escapes package")
    return p


def finite(v):
    if isinstance(v, float) and not math.isfinite(v):
        raise ValueError("nonfinite number")
    if isinstance(v, dict):
        for x in v.values():
            finite(x)
    if isinstance(v, list):
        for x in v:
            finite(x)


def pairs(items):
    d = {}
    for k, v in items:
        if k in d:
            raise ValueError("duplicate JSON key")
        d[k] = v
    return d


def load(p):
    v = json.loads(read(p), object_pairs_hook=pairs)
    finite(v)
    return v


def canonical(v):
    return json.dumps(
        v, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode()


def digest(b):
    return hashlib.sha256(b).digest()


def u(n):
    return struct.pack("<I", n)


def f(xs):
    return struct.pack("<" + "f" * len(xs), *xs)


def string(s):
    b = s.encode("ascii")
    return u(len(b)) + b


def count(n, maximum, minimum=1):
    if type(n) is not int or not minimum <= n <= maximum:
        raise ValueError("count out of bounds")
    return n


def vector(v, n):
    if (
        not isinstance(v, list)
        or len(v) != n
        or any(
            type(x) not in (int, float) or not math.isfinite(x) or abs(x) > 1e6
            for x in v
        )
    ):
        raise ValueError("invalid vector")
    return v
