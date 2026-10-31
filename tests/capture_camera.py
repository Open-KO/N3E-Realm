"""The camera a scene capture drew (PQ-355), for suites that compare captures
of separate test-client runs.

With N3E_TEST_EQUIPMENT_GLOW_CAPTURES or N3E_TEST_ATTACHMENT_CAPTURES the test
client prints, after each EQUIPMENT_GLOW_CAPTURE or ATTACHMENT_CAPTURE line,

    CAPTURE_CAMERA at=<s> yaw=<rad> pitch=<rad> distance=<m> self=<x>,<y>,<z>

the orbit it drew that frame with and the controlled character's predicted
position (client/render/viewer.cpp). Those clients never edge-yaw (the capture
replays own the camera), so every capture a suite compares should share one
view. A turned camera or a moved player then fails here, by name, before any
pixel is compared: PQ-350's desktop run instead failed the Durandal check with
the other player's blade 11 px off (the glow-on run's frame-40 world detail
differed from every other kept run's: its camera had turned).
"""
import re

LINE = re.compile(r'^CAPTURE_CAMERA at=([0-9.e+-]+) yaw=(\S+) pitch=(\S+) distance=(\S+) self=(\S+),(\S+),(\S+)$',
                  re.M)
# Printed to 5 decimals (angles), 4 (distance) and 3 (position).
TOLERANCE = 2e-3


def views(text):
    """[(capture second, (yaw, pitch, distance, x, y, z))] in print order."""
    return [(float(at), tuple(float(v) for v in rest)) for at, *rest in LINE.findall(text)]


class SameView:
    """Every client run checked must have drawn all its captures with one view,
    the first checked run's."""

    def __init__(self):
        self.first = None

    def check(self, name, text):
        seen = views(text)
        assert seen, f'{name}: no CAPTURE_CAMERA line (a test client without PQ-355?)'
        at, view = seen[0]
        for t, v in seen[1:]:
            assert all(abs(p - q) <= TOLERANCE for p, q in zip(v, view)), (
                f'{name}: the camera or the local player moved between its captures (PQ-355)', seen)
        if self.first is None:
            self.first = name, view
        else:
            assert all(abs(p - q) <= TOLERANCE for p, q in zip(view, self.first[1])), (
                f'{name} drew another view than {self.first[0]} (PQ-355): the camera turned or the local '
                'player moved between client runs', view, self.first[1])
        return view

    def summary(self):
        if self.first is None:
            return 'no view checked'
        yaw, pitch, distance, x, y, z = self.first[1]
        return f'yaw {yaw:.4f}, pitch {pitch:.4f}, distance {distance:.3f}, self at {x:.2f},{y:.2f},{z:.2f}'
