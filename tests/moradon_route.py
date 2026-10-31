"""Engine-verified Moradon demo routes from the town-square start to the worm areas.

The package builder proves these waypoints with the engine solver on every build
and records them in build/ko-moradon/provenance.json (original demo data, not KO).
"""
import json
from pathlib import Path

from moradon_stack import PROVENANCE


def worm_areas():
    return json.loads(PROVENANCE.read_text())['features']['worm']


def to_worms(walk, index=0):
    """Walk from the start to worm area `index`. Area 0's route is robust to a
    0.7 m stop tolerance on every leg; area 1's last leg is narrow."""
    for x, z in worm_areas()[index]['route']:
        walk(x, z)


def to_start(walk, spawn, index=0):
    """Walk back from worm area `index` through the same waypoints to `spawn`."""
    for x, z in reversed(worm_areas()[index]['route'][:-1]):
        walk(x, z)
    walk(*spawn)


def walker(p, first, tolerance=.25):
    """Return walk(x, z) for one peer: steer each tick, send a movement only after
    the server acknowledged the previous one (one movement per tick), and allow
    time in proportion to the leg length."""
    import math
    import time

    def walk(x, z, tol=tolerance):
        here = p.entities[p.id]
        end = time.monotonic() + 30 + math.hypot(x - first(here, 3), z - first(here, 5)) / 1.5
        while time.monotonic() < end:
            p.pump(.05)
            me = p.entities[p.id]
            if first(me, 6) < p.seq:
                continue
            dx, dz = x - first(me, 3), z - first(me, 5)
            d = math.hypot(dx, dz)
            if d < tol:
                p.move(0, 0); p.pump(.2); return
            p.move(dx / max(1, d), dz / max(1, d), mode=1)
        raise AssertionError(('blocked route', x, z, p.entities[p.id]))
    return walk
