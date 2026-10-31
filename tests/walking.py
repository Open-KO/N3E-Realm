"""Independent analytic movement cases; identical fixture input in C++ and Rust."""

import math
import pathlib
import subprocess

B = pathlib.Path("build/walking")
B.mkdir(parents=True, exist_ok=True)


def plane(slope=0):
    return [
        (-2, -2 * slope, -2),
        (2, 2 * slope, -2),
        (2, 2 * slope, 2),
        (-2, -2 * slope, -2),
        (2, 2 * slope, 2),
        (-2, -2 * slope, 2),
    ]


def case(name, triangles, start, inputs, config=None):
    path = B / (name + ".txt")
    values = (
        [len(triangles)]
        + [f for v in triangles for f in v]
        + list(start)
        + [f for v in inputs for f in v]
    )
    path.write_text(" ".join(map(str, values)) + "\n")
    outputs = []
    for command in [
        ["build/client/n3e-walk-check", str(path)],
        ["target/debug/n3e-server", "--walk-fixture", str(path)],
    ]:
        p = subprocess.run(
            command + (list(map(str, config)) if config else []),
            check=True,
            capture_output=True,
            text=True,
        )
        outputs.append(
            [list(map(float, line.split())) for line in p.stdout.splitlines()]
        )
    assert len(outputs[0]) == len(inputs)
    assert max(abs(a - b) for x, y in zip(*outputs) for a, b in zip(x, y)) < 1e-6, name
    return outputs[0]


p = case("diagonal", plane(), [0, 0, 0], [(1, 1)] * 10)[-1]
assert abs(math.hypot(p[0], p[2]) - 1.5) < 1e-6
p = case("slope", plane(0.5), [0, 0, 0], [(1, 0)] * 10)[-1]
assert abs(p[0] - 1.5) < 1e-6 and abs(p[1] - 0.75) < 1e-6
p = case("steep", plane(2), [0, 0, 0], [(1, 0)] * 10)[-1]
assert p == [0, 0, 0]
p = case("boundary", plane(), [0, 0, 0], [(1, 0)] * 100)[-1]
assert 1.8 < p[0] <= 2
walls = [
    (0.5, 0, -2),
    (0.5, 2, -2),
    (0.5, 2, 2),
    (0.5, 0, -2),
    (0.5, 2, 2),
    (0.5, 0, 2),
]
p = case("wall-slide", plane() + walls, [0, 0, 0], [(1, 1)] * 10)[-1]
assert p[0] < 0.3 and p[2] > 0.9
print(
    "PASS C++/Rust walking: normalized diagonal, 26-degree slope, steep rejection, boundary, wall sliding (1e-6m)"
)


# KO-01 policy cases use the very same production solver in both languages.
def large_plane(slope=0):
    return [(x * 10, y * 10, z * 10) for x, y, z in plane(slope)]


policy = [1.5, 4.5, 1.5, 0.2, 1.6, 0.25]
for speed in [0.01, 1.5, 3, 4.5, 6]:
    cfg = [speed, speed, speed, 0.1, 0.5, 0.05]
    for mode in range(3):
        for d in [(1, 0), (1, 1), (-1, 0), (0, 0), (0.25, 0)]:
            p = case(
                f"mode-{speed}-{mode}-{d}",
                large_plane(),
                [0, 0, 0],
                [(*d, mode)] * 20,
                cfg,
            )[-1]
            expected = speed * min(1, math.hypot(*d))
            assert abs(math.hypot(p[0], p[2]) - expected) < 2e-5, (speed, mode, p)
for mode, speed in enumerate([1.5, 4.5, 1.5]):
    p = case(
        f"policy-{mode}", large_plane(0.5), [0, 0, 0], [(1, 0, mode)] * 20, policy
    )[-1]
    assert abs(p[0] - speed) < 2e-5 and abs(p[1] - speed * 0.5) < 2e-5
    p = case(
        f"steep-{mode}", large_plane(1.01), [0, 0, 0], [(1, 0, mode)] * 20, policy
    )[-1]
    assert p == [0, 0, 0]
    p = case(
        f"thin-slide-{mode}",
        large_plane() + walls,
        [0, 0, 0],
        [(1, 1, mode)] * 10,
        policy,
    )[-1]
    assert p[0] <= 0.300001 and p[2] > speed * 0.3
# Fastest supported step would cross the diameter of the smallest wall radius
# without substeps. Repeat at offsets that place the wall between endpoints.
for offset in [0.101, 0.13, 0.16, 0.19]:
    wall = [(x - 0.5 + offset, y, z) for x, y, z in walls]
    p = case(
        f"thin-{offset}",
        large_plane() + wall,
        [0, 0, 0],
        [(1, 0, 1)] * 10,
        [6, 6, 6, 0.1, 1.6, 0.25],
    )[-1]
    assert p[0] <= offset - 0.1 + 1e-6, p


def ledge(height):
    return [
        (-2, 0, -2),
        (0, 0, -2),
        (0, 0, 2),
        (-2, 0, -2),
        (0, 0, 2),
        (-2, 0, 2),
        (0, height, -2),
        (2, height, -2),
        (2, height, 2),
        (0, height, -2),
        (2, height, 2),
        (0, height, 2),
    ]


for mode in range(3):
    p = case(
        f"step-pass-{mode}", ledge(0.2), [-0.5, 0, 0], [(1, 0, mode)] * 12, policy
    )[-1]
    assert p[0] > 0 and abs(p[1] - 0.2) < 1e-6, p
    p = case(
        f"step-fail-{mode}", ledge(0.3), [-0.5, 0, 0], [(1, 0, mode)] * 12, policy
    )[-1]
    assert p[0] < 0 and p[1] == 0, p
p = case(
    "mode-changes",
    large_plane(),
    [0, 0, 0],
    [(1, 0, 0)] * 20 + [(1, 0, 1)] * 20 + [(0, 0, 1)] * 20 + [(-1, 0, 2)] * 20,
    policy,
)[-1]
assert abs(p[0] - 4.5) < 2e-5, p
print(
    "PASS KO-01 modes/speed bounds, analog/diagonal/stop, slopes, steps, thin-wall substeps and sliding; C++/Rust agree 1e-6m"
)
# Dimensions must affect both solvers, rather than only release identity.
beam = [(x, y + 1.2, z) for x, y, z in walls]
p = case('low-body', large_plane() + beam, [0, 0, 0], [(1, 0, 1)] * 10,
         [1.5, 4.5, 1.5, .2, .5, .25])[-1]
assert p[0] > 2
p = case('tall-body', large_plane() + beam, [0, 0, 0], [(1, 0, 1)] * 10, policy)[-1]
assert p[0] <= .300001
p = case('wide-body', large_plane() + walls, [0, 0, 0], [(1, 0, 1)] * 10,
         [1.5, 4.5, 1.5, .4, 1.6, .25])[-1]
assert p[0] <= .100001
p = case('small-step', ledge(.2), [-.5, 0, 0], [(1, 0, 1)] * 10,
         [1.5, 4.5, 1.5, .2, 1.6, .1])[-1]
assert p[0] < 0
print('PASS package radius, height and step dimensions change collision identically')

for mode, speed in enumerate([1.5, 4.5, 1.5]):
    p = case(f'turbo-{mode}', large_plane(), [0,0,0], [(1,0,mode)]*4, policy+[10])[-1]
    assert abs(p[0]-speed*2) < 2e-5, p
for offset in [.101,.13,.16,.19,1.3,2.4]:
    wall=[(x-.5+offset,y,z) for x,y,z in walls]
    p=case(f'turbo-wall-{offset}',large_plane()+wall,[0,0,0],[(1,0,1)]*4,[6,6,6,.1,1.6,.25,10])[-1]
    assert p[0] <= offset-.1+1e-6,p
p=case('turbo-steep',large_plane(1.01),[0,0,0],[(1,0,1)]*4,policy+[10])[-1]
assert p==[0,0,0]
print('PASS turbo 10x modes, thin-wall collision and steep slopes; indexed C++ matches full Rust solver')

# A second walkable layer is a ceiling when it cannot be reached by a step.
# The old highest-surface query stopped at its footprint, even far overhead.
def canopy(height):
    return [(max(0, x), height, z) for x, _, z in plane()]

for multiplier in [1, 10]:
    cfg = policy + [multiplier]
    ticks = 12 if multiplier == 1 else 2
    for reverse in [False, True]:
        roof = canopy(3)
        if reverse:
            roof = list(reversed(roof))
        p = case(f'roof-step-{multiplier}-{reverse}', ledge(.2) + roof,
                 [-.5, 0, 0], [(1, 0, 1)] * ticks, cfg)[-1]
        assert p[0] > 1 and abs(p[1] - .2) < 1e-6, p
        p = case(f'roof-return-{multiplier}-{reverse}', ledge(.2) + roof,
                 [1, .2, 0], [(-1, 0, 1)] * ticks, cfg)[-1]
        assert p[0] < 0 and abs(p[1]) < 1e-6, p
    for height in [.3, 1.5, 1.7]:
        p = case(f'roof-headroom-{multiplier}-{height}', ledge(.2) + canopy(height),
                 [-.5, 0, 0], [(1, 0, 1)] * ticks, cfg)[-1]
        assert p[0] < 0 and p[1] == 0, p
    p = case(f'roof-no-support-{multiplier}', canopy(3),
             [-.5, 0, 0], [(1, 0, 1)] * ticks, cfg)[-1]
    assert p == [-.5, 0, 0], p
    # Walking on the upper storey must retain it, rather than select below.
    p = case(f'roof-upper-{multiplier}', plane() + canopy(3),
             [.2, 3, 0], [(1, 0, 1)] * ticks, cfg)[-1]
    assert p[0] > 1 and p[1] == 3, p
print('PASS layered support: roof entry/return, step beneath roof, low ceilings, '
      'missing support and upper storey at normal/turbo speed; C++/Rust agree')

# Real steps have vertical risers; the earlier ledge fixtures omitted them.
for height in [.06, .1, .2, .25, .251, .3, 2]:
    riser = [(0, 0, -2), (0, height, -2), (0, height, 2),
             (0, 0, -2), (0, height, 2), (0, 0, 2)]
    geometry = ledge(height) + riser
    for multiplier in [1, 10]:
        for mode in range(3):
            ticks = (36 if mode != 1 else 12) if multiplier == 1 else 4
            p = case(f'riser-{height}-{multiplier}-{mode}', geometry, [-.5, 0, 0],
                     [(1, 0, mode)] * ticks, policy + [multiplier])[-1]
            if height <= .25:
                assert p[0] > 1 and abs(p[1] - height) < 1e-6, p
                p = case(f'riser-return-{height}-{multiplier}-{mode}', geometry,
                         [1, height, 0], [(-1, 0, mode)] * ticks, policy + [multiplier])[-1]
                assert p[0] < 0 and abs(p[1]) < 1e-6, p
            else:
                assert p[0] <= -.2 + 1e-6 and p[1] == 0, p
    p = case(f'riser-small-policy-{height}', geometry, [-.5, 0, 0],
             [(1, 0, 1)] * 12, [1.5, 4.5, 1.5, .2, 1.6, .05])[-1]
    assert p[0] <= -.2 + 1e-6 and p[1] == 0, p
print('PASS closed risers: step-limit admission, descent, over-limit blocking, '
      'package limit, all modes and normal/turbo; C++/Rust agree')
