"""KO weapon effects in Moradon (PQ-211), against the prepared Moradon stack.

The Moradon package maps its blade to KO item 120110048 (Short Blade, Item_Ext_1
row 48, Burning +8), whose extension names fx.tbl effect 12001
(fx/fire_sword0_1.fxb) and its tail 12002 with the fire trace colour; the cook
turns the blade plug's FX mesh into an N3E2 appearance effect (ko_weapon_fx.py),
since PQ-376 (D-200) in N3E5 with 1298's alpha-list sort record: the plug
origin and the FX mesh's y extent (00415910), each tail spark keyed on its own
(004840b0). The fire effect blends with destination ONE on both draws, so its
pixels do not depend on that order.

Two fresh accounts equip the blade in the right hand over the wire. With
N3E_GRAPHICAL=1 the test client logs in as the first while the second stands
beside the spawn: the client must draw the effect on both (three FX mesh copies,
two tails, trace ffffff00), end the other player's when it unequips and start it
again on the re-equip; the capture must hold more warm glow pixels than the one
taken with Option.ini WeaponEffect.EffectVisible=0, which draws none. Captures
stay under build/pq211/moradon (KO artwork; never committed). No user
character is touched.

PQ-361 (D-196): the same KO item gives the blade 1298's tooltip head (004d6320).
Statically, the package's item-heads.bin (N3IH) holds exactly one head, the
blade's: name c87cc7 (attribute 5, the constructor 004d5bd0's +0xc0), the kind
line "(Upgrade Item)" (text 6812) in c87cc7 and the type line "One-handed
Sword" (00614940 for kind 21, text 2529) in white, no token, and the cook's
record names Item_Ext_1 row 48. Graphically, the first account's inventory
with the blade in its right hand shows the tooltip "Practice blade" in
c87cc7 with those two lines under it, each centred, and in the capture each
row's glyph band holds pixels of its colour beyond the same band of the
capture taken before the hover (tests/tooltip_head.py). Captures under
build/pq361/moradon.
"""
import json
import math
import os
import pathlib
import re
import secrets
import select
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from world_peer import Peer, blob, fields, first, integer  # noqa: E402
import moradon_stack  # noqa: E402
import npc_looks_live  # noqa: E402
import tooltip_head  # noqa: E402
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools/assetc'))
import item_heads  # noqa: E402

root = pathlib.Path(__file__).resolve().parents[1]
os.chdir(root)
state = moradon_stack.state()
package = (root / moradon_stack.PACKAGE).resolve()
recipe = json.loads((package / 'recipe.json').read_text())['manifest']
assert state['release'] == (package / 'release.sha256').read_text().strip()
assert (package / 'effects.bin').read_bytes()[:4] == b'N3E5', 'cook the Moradon package with PQ-376'
# PQ-376: each of the blade's effects sorts its copies at the plug origin plus
# the Short Blade FX mesh's y extent (0.833 m, PQ-373 claim 14).
effects = json.loads(moradon_stack.PROVENANCE.read_text())['effects']['appearance']
assert effects and all(abs(e['sort']['bias'] - .833) < 1e-3 for e in effects), effects
print(f"PASS Moradon package: effects.bin is N3E5; the blade's {len(effects)} weapon effects carry 1298's sort "
      f"record, bias {effects[0]['sort']['bias']:.4f} (the FX mesh's y extent)", flush=True)
# PQ-361 (D-196): the blade's 1298 tooltip head, the package's only one.
UPGRADE, WHITE = 0xc87cc7, 0xffffff
HEAD = [('(Upgrade Item)', UPGRADE), ('One-handed Sword', WHITE)]
labels = {i['id']: i['label'] for i in recipe['inventory']['items']}
assert item_heads.parse((package / 'item-heads.bin').read_bytes(), recipe['game_id'], set(labels)) == (
    '', {'demo:item/blade': (UPGRADE, HEAD)}), 'cook the Moradon package with PQ-361'
record, = json.loads(moradon_stack.PROVENANCE.read_text())['item_heads_1298']
assert (record['ko_item'], record['item_ext'], record['attribute'], record['kind'], record['texts']) == (
    120110048, 'Item_Ext_1 row 48', 5, 21, [6812, 2529]), record
print('PASS Moradon package: the blade (KO item 120110048, Item_Ext_1 row 48, attribute 5) carries 1298\'s '
      'tooltip head: c87cc7, "(Upgrade Item)" c87cc7, "One-handed Sword" ffffff', flush=True)
env = {**os.environ, 'N3E_IMAGE': moradon_stack.IMAGE, 'N3E_PACKAGE_PATH': str(package), 'N3E_PORT': str(state['port']),
       'N3E_REALM': state['realm']}
work = root / 'build/pq211/moradon'
work.mkdir(parents=True, exist_ok=True)
TRACE = 'ffffff00'
accounts = {}
for role in ('explorer', 'companion'):
    account = 'wfx' + role[:4] + secrets.token_hex(5)
    password = secrets.token_urlsafe(24)
    subprocess.run(['docker', 'compose', '-p', moradon_stack.PROJECT, 'exec', '-T', 'server', 'n3e-server',
                    'account-create', account], input=password + '\n', text=True, env=env, capture_output=True,
                   check=True)
    accounts[role] = (account, password)
serial = [0]


def peer(role):
    account, password = accounts[role]
    p = Peer(state['port'], account, password, content=state['release'], game=recipe['game_id'],
             protocol=recipe['protocol_version'])
    p.select(p.create(role.title() + secrets.token_hex(3)))
    return p


def wait(p, tag, predicate=lambda d: True, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        t, d = p.receive()
        assert t != 4, (t, d)
        if t == tag and predicate(d):
            return d
    raise AssertionError(('timeout', tag))


def bag(p, op=0, source=0, destination=0, s=None):
    time.sleep(.22)  # inside the shared inventory request budget
    if not op:
        p.send(32, b'')
        return fields(first(wait(p, 33, lambda d: first(d, 2) == b'ok'), 3))
    serial[0] += 1
    records = s[6] if op == 6 else s[5]
    p.send(32, integer(1, op) + blob(2, f'pq211-{secrets.token_hex(4)}-{serial[0]}') + integer(3, first(s, 1))
           + integer(4, source) + integer(5, destination) + integer(6, first(fields(records[source]), 1)))
    d = wait(p, 33)
    assert first(d, 2) == b'committed', d
    return fields(first(d, 3))


def keys(p):
    return list(first(p.entities.get(p.id, {}), 20, b''))


def equip(p):
    s = bag(p)
    assert first(fields(s[5][0]), 2) == b'demo:item/blade', s[5][0]
    s = bag(p, 5, 0, 0, s)
    wait(p, 10, lambda _: keys(p) == [1])
    return s


def drain(p):
    while p.s.pending() or select.select([p.s], [], [], 0)[0]:
        t, d = p.receive()
        assert t != 4, (t, d)


def walk(p, x, z, seconds=20):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        p.pump(.05)
        me = p.entities[p.id]
        if first(me, 6) < p.seq:
            continue
        dx, dz = x - first(me, 3), z - first(me, 5)
        d = math.hypot(dx, dz)
        if d < .3:
            p.move(0, 0)
            p.pump(.2)
            return True
        p.move(dx / max(1, d), dz / max(1, d), mode=0)
    p.move(0, 0)
    return False


a = peer('explorer')
equip(a)
a.logout()
b = peer('companion')
b_state = equip(b)
sx, sz = recipe['gameplay']['spawn_x'], recipe['gameplay']['spawn_z']
# Ahead of the camera's opening view (towards -z), else the first open side.
for dx, dz in ((0, -2.5), (2.5, 0), (-2.5, 0), (0, 2.5)):
    if walk(b, sx + dx, sz + dz):
        break
print('PASS two Moradon accounts equip the Burning +8 blade over the wire and carry appearance key 1', flush=True)
if os.environ.get('N3E_GRAPHICAL') != '1':
    b.logout()
    sys.exit(0)
other = b.id
line = r'^APPEARANCE_EFFECT entity={} self={} key=1 copies=3 vertices=36 tails=2 trace=' + TRACE + ' '
held = {}


def client(capture, config, steps=()):
    lines = []
    account, password = accounts['explorer']
    proc = subprocess.Popen(
        ['build/client/n3e-test-client', str(package), '--connect', 'localhost:' + str(state['port']), '--ca',
         'deploy/local/ca.pem', '--auto-login', '--fixed-window', '1280x1024', '--world-smoke', '20',
         '--capture', str(capture)],
        env={**env, 'N3E_TEST_ACCOUNT': account, 'N3E_TEST_PASSWORD': password, 'N3E_TEST_APPEARANCE_EFFECTS': '1',
             'XDG_CONFIG_HOME': config}, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    reader = threading.Thread(target=lambda: lines.extend(proc.stdout), daemon=True)
    reader.start()
    pending = list(steps)
    while proc.poll() is None:
        b.pump(.1)
        if pending and pending[0][0](''.join(lines)):
            pending.pop(0)[1]()
    reader.join(10)
    text = ''.join(lines)
    capture.with_suffix('.log').write_text(text)
    assert proc.returncode == 0 and capture.stat().st_size > 0, (proc.returncode, text[-1500:])
    assert not pending, ('steps not reached', len(pending), text[-1500:])
    return text


def found(*patterns):
    return lambda text: all(re.search(p, text, re.M) for p in patterns)


def unequip():
    held['s'] = bag(b, 6, 0, 0, b_state)
    wait(b, 10, lambda _: keys(b) == [])


def reequip():
    bag(b, 5, 0, 0, held['s'])
    wait(b, 10, lambda _: keys(b) == [1])


def warm(path):
    """Pixels of the fire glow's colour: bright, red and green well above blue."""
    width, height, pixels = npc_looks_live.read_ppm(path)
    count = 0
    for y in range(height // 10, height * 7 // 10):
        row = y * width * 3
        for x in range(width // 10, width * 9 // 10):
            r, g, b_ = pixels[row + 3 * x:row + 3 * x + 3]
            count += r > 200 and g > 140 and b_ < 120 and r - b_ > 110
    return count


with tempfile.TemporaryDirectory(dir=root / 'build') as config:
    shown = work / 'weapon-effects-on.ppm'
    text = client(shown, config, steps=[
        (found(line.format(r'\d+', 1), line.format(other, 0)), unequip),
        (found(rf'^APPEARANCE_EFFECT_END entity={other} key=1$'), reequip)])
    mine, others = re.findall(line.format(r'\d+', 1), text, re.M), re.findall(line.format(other, 0), text, re.M)
    assert len(mine) == 1 and len(others) == 2, (mine, others, text[-2000:])
    print('PASS Moradon client draws the Burning +8 blade effect on itself and on the other player, ends the '
          "other's on its unequip and starts it again on its re-equip", flush=True)
    pathlib.Path(config, 'n3e').mkdir()
    pathlib.Path(config, 'n3e', 'Option.ini').write_text('[WeaponEffect]\nEffectVisible=0\n')
    hidden = work / 'weapon-effects-off.ppm'
    assert 'APPEARANCE_EFFECT' not in client(hidden, config)
on, off = warm(shown), warm(hidden)
assert on > off + 150, (on, off)
print(f'PASS Moradon weapon effect graphical: {on} warm glow pixels with the effect, {off} with '
      f'WeaponEffect.EffectVisible=0; {shown}, {hidden}', flush=True)


def blade_view():
    """PQ-361: the first account's inventory, the blade in its right hand: the
    tooltip head as 1298's 004d6320 draws it for 120110048."""
    shot = root / 'build/pq361/moradon/blade-gear'
    shot.parent.mkdir(parents=True, exist_ok=True)
    account, password = accounts['explorer']
    with tempfile.TemporaryDirectory(dir=root / 'build') as config:
        proc = subprocess.run(
            ['build/client/n3e-test-client', str(package), '--connect', 'localhost:' + str(state['port']), '--ca',
             'deploy/local/ca.pem', '--auto-login', '--fixed-window', '1280x1024', '--world-smoke', '60',
             '--capture', str(shot)],
            env={**env, 'N3E_TEST_ACCOUNT': account, 'N3E_TEST_PASSWORD': password, 'N3E_TEST_ITEM_TOOLTIP': 'blade',
                 'N3E_TEST_ITEMS': 'blade=demo:item/blade', 'XDG_CONFIG_HOME': config},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
    text = proc.stdout
    shot.with_suffix('.log').write_text(text)
    assert proc.returncode == 0, (proc.returncode, text[-2000:])
    slot = re.findall(r'^ITEM_SLOT key=(gear:\d+) item=demo:item/blade icon=\d rect=', text, re.M)
    assert len(slot) == 1, text[-2000:]
    shots = {name: pathlib.Path(f'{shot}.item-{name}.ppm') for name in ('slot', 'tooltip')}
    assert all(p.stat().st_size > 0 for p in shots.values()), shots
    head, _ = tooltip_head.check(text, slot[0], shots['tooltip'], [(labels['demo:item/blade'], UPGRADE)] + HEAD,
                                 base=shots['slot'])
    print(f'PASS Moradon client draws the blade\'s 1298 tooltip head in {slot[0]} (row, colour, pixels of it, '
          f'without the tooltip): {head}; {shots["tooltip"]}', flush=True)


drain(b)
b.logout()
blade_view()
