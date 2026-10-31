"""Reference Moradon worm (N3N2) against the running local realm, over real TLS.

Run tools/play-moradon --no-build --provision-only first. Uses a disposable
account; no user character is modified. Checks the player start area, worm
placement inside the KO spawn rectangles, passivity, retaliation at the reference
attack interval, and slot respawn delay and placement.
"""
import json, math, os, secrets, subprocess, time
from pathlib import Path
from world_peer import Peer, first
import moradon_stack

state = moradon_stack.state()
package = moradon_stack.PACKAGE
m = json.loads((package / 'recipe.json').read_text())['manifest']
assert m['engine_version'] >= 36 and m['npc']['model'] == 'reference_melee_v2'
assert state['release'] == (package / 'release.sha256').read_text().strip()
report = json.loads(moradon_stack.PROVENANCE.read_text())['features']['worm']
env = {**os.environ, 'N3E_IMAGE': moradon_stack.IMAGE, 'N3E_PACKAGE_PATH': str(package.resolve()),
       'N3E_PORT': str(state['port']), 'N3E_REALM': state['realm']}
account = 'worm' + secrets.token_hex(5); password = secrets.token_urlsafe(24)
subprocess.run(['docker', 'compose', '-p', moradon_stack.PROJECT, 'exec', '-T', 'server', 'n3e-server', 'account-create', account],
               input=password + '\n', env=env, text=True, capture_output=True, check=True)
p = Peer(state['port'], account, password, content=state['release'], game=m['game_id'], protocol=m['protocol_version'])
p.select(p.create('Worm' + secrets.token_hex(3))); p.pump(.5)
g = m['gameplay']; interval = g['npc_cooldown_ticks']


def me(): return p.entities[p.id]


def worms(): return [e for e in p.entities.values() if first(e, 9) and first(e, 7)]


def inside(e, area):
    return area[0] <= first(e, 3) <= area[2] and area[1] <= first(e, 5) <= area[3]


def walk(x, z, tolerance=.5, seconds=40):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        p.pump(.05); dx = x - first(me(), 3); dz = z - first(me(), 5); d = math.hypot(dx, dz)
        if d < tolerance: p.move(0, 0); p.pump(.2); return
        p.move(dx / max(1, d), dz / max(1, d), mode=1)
    raise AssertionError(('route blocked', x, z, first(me(), 3), first(me(), 5)))


try:
    start = m['gameplay']
    x0, z0 = first(me(), 3), first(me(), 5)
    # KO START_POSITION zone 21: (306, 352) +/- 10 -> n3e x 40..60, z -106..-86.
    assert 40 <= x0 <= 60 and -106 <= z0 <= -86 and (x0, z0) == (start['spawn_x'], start['spawn_z']), (x0, z0)
    print('PASS player starts inside the reference Moradon start rectangle', [x0, z0])
    # Area 0 has the route that tolerates imprecise stops on every leg.
    area = report[0]; seconds = area['respawn_seconds']
    for x, z in area['route']: walk(x, z)
    p.pump(1)
    seen = [e for e in worms() if first(e, 2) == g['npc'].encode()]
    assert seen, 'no worm in interest at area B'
    for e in seen:
        # Idle passive worms stand at their spawn home: an integer point in a KO area.
        assert first(e, 12) == b'idle' and any(inside(e, w['area']) for w in report), e
        assert first(e, 3) == int(first(e, 3)) and first(e, 5) == int(first(e, 5)), e
        assert first(e, 7) == g['npc_health'] == 7, e
    print('PASS', len(seen), 'visible worms idle at integer points inside the KO spawn rectangles with 7 HP')
    # Passive: standing beside a worm for longer than scan and acquisition never provokes it.
    target = min((e for e in seen if inside(e, area['area'])),
                 key=lambda e: math.hypot(first(e, 3) - first(me(), 3), first(e, 5) - first(me(), 5)))
    tid = first(target, 1); walk(first(target, 3) - .6, first(target, 5), tolerance=.3)
    hp = first(me(), 7); p.pump(4)
    assert first(p.entities[tid], 12) == b'idle' and first(me(), 7) == hp, (p.entities[tid], hp)
    print('PASS passive worm ignores an adjacent player for 4 s')
    # Unarmed hits provoke retaliation; worm strikes follow the reference 2000 ms interval.
    # One accepted hit provokes it; the player then stands still. Swinging on
    # (2-3 damage a hit, 1000 ms apart) raced the 7 HP worm's death against its
    # second strike: a lethal third swing on the tick that strike fell due
    # resolved first, leaving one strike (PQ-438).
    full = first(p.entities[tid], 7); end = time.monotonic() + 30
    while tid in p.entities and first(p.entities[tid], 7) == full and time.monotonic() < end:
        result = p.action(tid)
        assert result in ('hit', 'miss', 'cooldown', 'combat_pending', 'target_pending'), result
        p.pump(.15)
    assert tid in p.entities and 0 < first(p.entities[tid], 7) < full, ('no surviving damaged worm', p.entities.get(tid))
    strikes = []; end = time.monotonic() + 20
    while tid in p.entities and len(strikes) < 3 and time.monotonic() < end:
        tick = first(p.entities[tid], 10)
        if tick and (not strikes or tick != strikes[-1]): strikes.append(tick)
        p.pump(.05)
    # Retaliation is required, and with the player idle the worm lives to strike three times.
    assert len(strikes) == 3, ('no retaliation observed', strikes)
    gaps = [b - a for a, b in zip(strikes, strikes[1:])]
    assert all(gap >= interval for gap in gaps), gaps
    print('PASS passive worm retaliates after accepted damage; strike gaps', gaps, 'ticks (reference', interval, ')')
    # Finish it and time the slot respawn inside area B.
    end = time.monotonic() + 30
    while tid in p.entities and first(p.entities[tid], 7) > 0 and time.monotonic() < end:
        p.action(tid); p.pump(.15)
    dead = p.entities.get(tid)
    assert dead is None or first(dead, 7) == 0
    before = {first(e, 1) for e in worms()}
    died = p.tick
    end = time.monotonic() + seconds + 10
    fresh = []
    while time.monotonic() < end and not fresh:
        p.pump(.2)
        fresh = [e for e in worms() if first(e, 1) not in before and inside(e, area['area'])]
    assert fresh, ('no respawn inside the area within', seconds + 10, 's')
    elapsed = p.tick - died
    assert seconds * 20 - 40 <= elapsed <= seconds * 20 + 60, elapsed
    e = fresh[0]
    assert first(e, 3) == int(first(e, 3)) and first(e, 5) == int(first(e, 5)) and first(e, 7) == 7, e
    print('PASS killed worm respawns after', elapsed, 'ticks (', seconds, 's slot) at', [first(e, 3), first(e, 5)], 'inside its KO area')
    p.logout()
finally:
    p.s.close()
