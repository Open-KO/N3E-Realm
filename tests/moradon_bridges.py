"""Optional local-asset routes through both castle bridge exits, in both solvers.

Geometry is baked from the supplied assets, never committed as a test fixture.
Run after make client server. No display, service or character mutation needed.
"""
import json
import math
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path('tools/assetc').resolve()))
import ko_bake
import main

assets = Path('assets/ko/Zones')
if not all((assets / ('moradon_xmas.' + ext)).exists() for ext in ['gtd', 'opd']):
    print('SKIP Moradon bridge routes: optional local GTD/OPD assets absent')
    sys.exit(0)

height, faces, _ = ko_bake.bake(assets / 'moradon_xmas.gtd', assets / 'moradon_xmas.opd')
# Round through the collision format, exactly as the production readers do.
import struct
points = main.heightfield_triangles(height) + [p for t in faces for p in t]
points = [struct.unpack('<fff', struct.pack('<fff', *p)) for p in points]
prefix = ' '.join(map(str, [len(points)] + [v for p in points for v in p]))
out = Path('build/kx/bridge-routes')
out.mkdir(parents=True, exist_ok=True)
policy = ['1.5', '4.5', '1.5', '.2', '1.6', '.25']
report = []
for name, start, direction, run_ticks, modes, heights in [
    ('diagonal', [27.123259, 8.677688, -63.82403], [1, -1], 120, range(3), (8.6, 8.8)),
    ('straight', [138.7, 8.701923, 8.5], [0, -1], 120, range(3), (8.6, 8.8)),
    ('full-diagonal', [0, 7.218894, -36.7], [1, -1], 300, [1], (7, 8.8)),
    ('full-straight', [138.7, 7.339809, 40], [0, -1], 300, [1], (7, 8.8)),
    ('stair-diagonal', [58.277294, 8.715808, -91.86274], [1, -1], 120, [1], (8.6, 13.6)),
    ('stair-west', [20, 8.715808, -163.14], [1, 0], 120, [1], (8.6, 13.6)),
]:
    for mode in modes:
        for multiplier in [1, 10]:
            # 27m per gate/stair route; 67.5m for complete bridge approaches.
            ticks = run_ticks * (3 if mode != 1 else 1) // multiplier
            inputs = [direction + [mode]] * ticks + [[-v for v in direction] + [mode]] * ticks
            path = out / f'{name}-{mode}-{multiplier}.txt'
            path.write_text(prefix + ' ' + ' '.join(map(str, start + [v for p in inputs for v in p])))
            outputs = []
            for cmd in [['build/client/n3e-walk-check', str(path)],
                        ['target/debug/n3e-server', '--walk-fixture', str(path)]]:
                result = subprocess.run(cmd + policy + [str(multiplier)],
                                        check=True, capture_output=True, text=True)
                outputs.append([list(map(float, line.split())) for line in result.stdout.splitlines()])
            error = max(abs(a-b) for x,y in zip(*outputs) for a,b in zip(x,y))
            assert all(len(p) == len(inputs) for p in outputs)
            assert error < 1e-6, (name, mode, multiplier, error)
            p = outputs[0]
            away = math.hypot(start[0]-p[ticks-1][0], start[2]-p[ticks-1][2])
            returned = math.dist(start, p[-1])
            assert away > run_ticks * .225 - .1 and returned < .005, (name, mode, multiplier, away, returned)
            assert all(heights[0] < q[1] < heights[1] for q in p), (name, 'wrong support layer')
            if name.startswith('stair-'):
                assert p[ticks-1][1] > 13.4, (name, 'did not reach upper landing')
            report.append(dict(bridge=name, mode=mode, multiplier=multiplier,
                               away=away, returned=returned, solver_error=error))
(out / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
print('PASS actual Moradon gates, complete bridge approaches and two stair landings: '
      'round trips at normal/turbo, full Rust/indexed C++ agreement within 1e-6m')
