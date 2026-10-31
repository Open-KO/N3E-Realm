"""The 2233 client's equipment glow in Moradon (PQ-315, PQ-320), against the
prepared Moradon glow stack: a 2233/2145 addition (KO 1298 has none).

The package is the Moradon feature cook with --glow-2233 (packages/moradon-glow2233).
It carries two glow records on appearance.json rows (tools/assetc/ko_glow_2233.py;
the skeletal Azagai grades' records, PQ-337, are moradon_skeletal_plug_live's),
both drawn by the 2233 client's 0056ea30 as a pulse at MODULATE2X:

- key 3, the shield row: the Round Shield artwork is 2145 item 170251015
  (Item_Org 170251000, Item_Ext_36 row 15: attribute 11, column 45 = 15);
- key 4, the two-hander row (PQ-320): the glow cook draws Durandal's artwork
  (Item/1_2631_00_0.n3cplug, the row's glow_2233_source) in place of the
  Two-Handed Sword's, as 2145 item 126311011 (Item_Org 126311000, Item_Ext_26
  row 11: attribute 11, column 45 = 11). The item, its right-hand slot and the
  server's appearance key are the two-hander's; only the drawn mesh changes.

The glow package also names and draws that item as Durandal (PQ-321): its own
inventory definition (inventory.bin, N3I1, which the server's inventory policy
loads and hashes into every bag it keeps) labels demo:item/twohand "Durandal",
and its own item icon map draws it with UI/ItemIcon_1_2631_00_0.dxt, the icon
of the 1298 client's Item_Org row 126310000 (model and icon 12631000;
KnightOnLine.exe 006157b0 builds the icon path from the Item_Org icon).

For each case two fresh accounts equip the item over the wire (the shield in
the left hand, then, after unequipping it, the two-hander in the right). With
N3E_GRAPHICAL=1 the test client logs in as the first while the second stands
beside the spawn: the client must draw the glow on both (EQUIPMENT_GLOW key,
pulse, modulate 2), its sampled intensities must follow 0056ea30's curve on each
player's own clock through rise, hold and fall, the other player's glow must
end when it unequips and start again on the re-equip, and the captures must
show the glow: brighter at the item than one taken with Option.ini
[Addition2233] EquipmentGlow=0, which draws no glow. Both clients capture the
frame when the local player has been drawn for 7.5 s (its pulse holds at 1) and
for 10.75 s (the pulse is at 0, so only the 2x modulate is left). Captures stay
under build/pq320/moradon/<case> (KO artwork; never committed). Then the client
opens the first account's
inventory (N3E_TEST_ITEM_TOOLTIP), first with the two-hander still in its right
hand (the inventory window's equipment slot), then back in its bag: each slot's drawn icon
must match Durandal's icon texels, not the Two-Handed Sword's, and its tooltip
must read "Durandal" (captures under build/pq321/moradon/bag). No user
character is touched.
"""
import hashlib
import json
import math
import os
import pathlib
import re
import secrets
import select
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from world_peer import Peer, blob, fields, first, integer  # noqa: E402
import capture_camera  # noqa: E402
import moradon_stack  # noqa: E402
import npc_looks_live  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools/assetc'))
import ko_hud  # noqa: E402  (the HUD icon decoder, for the slot's texels)

root = pathlib.Path(__file__).resolve().parents[1]
os.chdir(root)
state = moradon_stack.state()
package = (moradon_stack.WORK / 'packages/moradon-glow2233').resolve()
assert state['release'] == (package / 'release.sha256').read_text().strip(), 'the stack must serve the glow package'
recipe = json.loads((package / 'recipe.json').read_text())['manifest']
# N3E3, or since PQ-342 N3E4 (the Azagai tail's camera-distance particle rules),
# or since PQ-376 N3E5 (the 1298 blade's alpha-list sort records).
assert (package / 'effects.bin').read_bytes()[:4] in (b'N3E3', b'N3E4', b'N3E5'), \
    'cook the Moradon package with --glow-2233'
provenance = json.loads((moradon_stack.WORK / 'ko-moradon-glow2233/provenance.json').read_text())
glows = provenance['glow_2233']['glow']
# The skeletal plug grades' glows (PQ-337) are moradon_skeletal_plug_live's,
# the Krowaz Assassin parts' (PQ-319) moradon_armour_live's.
assert [(g['key'], g['glow_2145_item'], g['wave'], g['modulate'], g.get('artwork')) for g in glows
        if 'skeletal_plug' not in g and 'armour_2145' not in g] == [
    (3, 170251015, 'pulse', 2, None), (4, 126311011, 'pulse', 2, 'Item/1_2631_00_0.n3cplug')], glows
drawn = provenance['render_detail']['appearances']
assert drawn[3]['item'] == 'demo:item/twohand' and drawn[3]['source'] == 'Item/1_2631_00_0.n3cplug', drawn[3]
# PQ-321: the glow package's own name and icon for the two-hander.
DURANDAL_ICON, TWOHAND_ICON = 'UI/ItemIcon_1_2631_00_0.dxt', 'UI/ItemIcon_1_2531_00_0.dxt'
shown = provenance['glow_2233']['presentation']['items']
assert [(x['item'], x['label'], x['icon'], x['item_org'], x['default_label'], x['default_icon']['base'])
        for x in shown] == [('demo:item/twohand', 'Durandal', 12631000, 126310000, 'Two hand blade', 12531000)], shown
icon_rows = {x['item']: x for x in provenance['hud']['item_icons']}
assert icon_rows['demo:item/twohand']['path'] == DURANDAL_ICON, icon_rows['demo:item/twohand']


def labels(data):
    """{item: label} of an N3I1 inventory definition (tools/assetc/inventory.py)."""
    at = [4]

    def u():
        at[0] += 4
        return struct.unpack_from('<I', data, at[0] - 4)[0]

    def text():
        n = u()
        at[0] += n
        return data[at[0] - n:at[0]].decode('ascii')
    assert data[:4] == b'N3I1', data[:4]
    u(), text(), u(), u()
    found = {}
    for _ in range(u()):
        item, label = text(), text()
        u(), u(), u()
        found[item] = label
    return found


inventory = (package / 'inventory.bin').read_bytes()
assert labels(inventory)['demo:item/twohand'] == 'Durandal', labels(inventory)
env = {**os.environ, 'N3E_IMAGE': moradon_stack.IMAGE, 'N3E_PACKAGE_PATH': str(package), 'N3E_PORT': str(state['port']),
       'N3E_REALM': state['realm']}
RIGHT, LEFT = 0, 1
CASES = [dict(name='shield', item=b'demo:item/shield', key=3, slot=LEFT, ko=170251015, label='Round Shield'),
         dict(name='durandal', item=b'demo:item/twohand', key=4, slot=RIGHT, ko=126311011, label='Durandal')]
# Seconds of the local player's clock: 7.5 % 5.5 = 2 (held at 1), 10.75 % 5.5 = 5.25 (0).
PEAK, TROUGH = 7.5, 10.75
# The blade check (lit_in): pixels at least LEVELS brighter, net of those as
# much darker, inside each player's blade box (the client's
# EQUIPMENT_GLOW_BOX, grown by PAD), at least these many: the peak over the
# option off, the trough (2x alone) over the option off, the peak over the
# trough. The idle sway alone moves up to about 40 pixels either way.
LEVELS, PAD = 30, 3
NEEDED = dict(peak=50, trough=25, pulse=25)
accounts = {}
for role in ('explorer', 'companion'):
    account = 'glow' + role[:4] + secrets.token_hex(5)
    password = secrets.token_urlsafe(24)
    subprocess.run(['docker', 'compose', '-p', moradon_stack.PROJECT, 'exec', '-T', 'server', 'n3e-server',
                    'account-create', account], input=password + '\n', text=True, env=env, capture_output=True,
                   check=True)
    accounts[role] = (account, password)
serial = [0]


def peer(role, create=True):
    account, password = accounts[role]
    p = Peer(state['port'], account, password, content=state['release'], game=recipe['game_id'],
             protocol=recipe['protocol_version'])
    p.select(p.create(role.title() + secrets.token_hex(3)) if create else p.characters[0][0])
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
    p.send(32, integer(1, op) + blob(2, f'pq320-{secrets.token_hex(4)}-{serial[0]}') + integer(3, first(s, 1))
           + integer(4, source) + integer(5, destination) + integer(6, first(fields(records[source]), 1)))
    d = wait(p, 33)
    assert first(d, 2) == b'committed', d
    return fields(first(d, 3))


def keys(p):
    return list(first(p.entities.get(p.id, {}), 20, b''))


def equip(p, case, s=None):
    """Equip the case's item from the bag; (state, the bag slot it came from)."""
    s = bag(p) if s is None else s
    at = next(i for i, r in enumerate(s[5]) if first(fields(r), 2) == case['item'])
    s = bag(p, 5, at, case['slot'], s)
    wait(p, 10, lambda _: keys(p) == [case['key']])
    return s, at


def unequip(p, case, s, at):
    """Return the case's item to bag slot `at`; the new state."""
    s = bag(p, 6, case['slot'], at, s)
    wait(p, 10, lambda _: keys(p) == [])
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


def expected(t):
    """0056ea30 (2233): i = t to 1 s, held to 3 s, 1 - (t - 3) x 0.5 to 5 s, 0 to
    5.5 s, then again from 0."""
    c = math.fmod(t, 5.5)
    return c if c <= 1 else 1 if c <= 3 else 1 - (c - 3) * .5 if c <= 5 else 0


def png(path, width, height, rows):
    raw = b''.join(b'\0' + bytes(r) for r in rows)
    chunk = lambda kind, data: (struct.pack('>I', len(data)) + kind + data  # noqa: E731
                                + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def groups(mask):
    """Pixel sets joined across gaps of up to 8 pixels, as (size, x0, y0, x1, y1)."""
    found = []
    while mask:
        stack, members = [mask.pop()], []
        while stack:
            x, y = stack.pop()
            members.append((x, y))
            for dy in range(-8, 9):
                for dx in range(-8, 9):
                    if (x + dx, y + dy) in mask:
                        mask.remove((x + dx, y + dy))
                        stack.append((x + dx, y + dy))
        xs, ys = [m[0] for m in members], [m[1] for m in members]
        found.append((len(members), min(xs), min(ys), max(xs), max(ys)))
    return sorted(found, reverse=True)


def warm(path):
    """Groups of bright warm pixels (red above 220, green above 120, red 70 over
    blue: the lit shield's brass at 2x) in the capture's middle (away from the
    HUD)."""
    w, h, pixels = npc_looks_live.read_ppm(path)
    mask = set()
    for y in range(h // 10, h * 8 // 10):
        for x in range(w // 10, w * 9 // 10):
            i = (y * w + x) * 3
            r, g, b = pixels[i:i + 3]
            if r > 220 and g > 120 and r - b > 70:
                mask.add((x, y))
    return groups(mask)


def lit_in(path, base, box, levels=LEVELS):
    """Pixels of `box` whose every channel is at least `levels` above the same
    pixel of `base`, less those `levels` below it: the idle sway between two
    captures moves a few pixels either way, a glow only lifts them."""
    w, h, pixels = npc_looks_live.read_ppm(path)
    _, _, under = npc_looks_live.read_ppm(base)
    x0, y0, x1, y1 = box
    net = 0
    for y in range(max(0, y0), min(h, y1 + 1)):
        for x in range(max(0, x0), min(w, x1 + 1)):
            i = (y * w + x) * 3
            net += all(pixels[i + c] >= under[i + c] + levels for c in range(3))
            net -= all(under[i + c] >= pixels[i + c] + levels for c in range(3))
    return net


def boxes(text, other):
    """{(capture second, 'self' or 'other'): the screen box of the glowing item
    (EQUIPMENT_GLOW_BOX), grown by PAD pixels}."""
    found = {}
    for at, entity, me, x0, y0, x1, y1 in re.findall(
            r'^EQUIPMENT_GLOW_BOX at=([0-9.]+) entity=(\d+) self=(\d) key=4 box=(-?\d+),(-?\d+),(-?\d+),(-?\d+)$',
            text, re.M):
        who = 'self' if me == '1' else 'other' if int(entity) == other else None
        assert who and (float(at), who) not in found, (at, entity, me, found)
        found[float(at), who] = (int(x0) - PAD, int(y0) - PAD, int(x1) + PAD, int(y1) + PAD)
    assert set(found) == {(t, w) for t in (PEAK, TROUGH) for w in ('self', 'other')}, found
    return found


def client(case, capture, config, b, steps=(), extra=None):
    lines = []
    account, password = accounts['explorer']
    proc = subprocess.Popen(
        ['build/client/n3e-test-client', str(package), '--connect', 'localhost:' + str(state['port']), '--ca',
         'deploy/local/ca.pem', '--auto-login', '--fixed-window', '1280x1024', '--world-smoke', '20',
         '--capture', str(capture)],
        env={**env, 'N3E_TEST_ACCOUNT': account, 'N3E_TEST_PASSWORD': password, 'N3E_TEST_EQUIPMENT_GLOW': '1',
             'N3E_TEST_EQUIPMENT_GLOW_CAPTURES': f'{PEAK},{TROUGH}', 'XDG_CONFIG_HOME': config, **(extra or {})},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
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
    # PQ-355: every run whose captures are compared drew one view.
    VIEW.check(capture.name, text)
    return text


# PQ-355: the view of the first capture run, which every later one must share.
VIEW = capture_camera.SameView()


def found(*patterns):
    return lambda text: all(re.search(p, text, re.M) for p in patterns)


def graphical(case, b, held):
    """The case's glow drawn on both players, the other's unequip and re-equip,
    the pulse samples, and the captures against the option off."""
    key, other = case['key'], b.id
    work = root / 'build/pq320/moradon' / case['name']
    work.mkdir(parents=True, exist_ok=True)
    start = r'^EQUIPMENT_GLOW entity={} self={} key=%d wave=pulse modulate=2 color=1,1,1 vertices=\d+$' % key
    end = rf'^EQUIPMENT_GLOW_END entity={other} key={key}$'

    def off():
        held['s'] = unequip(b, case, held['s'], held['at'])

    def on():
        held['s'], held['at'] = equip(b, case, held['s'])

    with tempfile.TemporaryDirectory(dir=root / 'build') as config:
        text = client(case, work / 'glow-on.ppm', config, b, steps=[
            (found(start.format(r'\d+', 1), start.format(other, 0)), off), (found(end), on)])
        assert 'a 2233/2145 addition (N3E3), on' in text, text[:1500]
        mine, others = re.findall(start.format(r'\d+', 1), text, re.M), re.findall(start.format(other, 0), text, re.M)
        ended = re.findall(end, text, re.M)
        assert len(mine) == 1 and len(others) == 2 and len(ended) == 1, (mine, others, ended, text[-2000:])
        assert not re.search(r'^EQUIPMENT_GLOW entity=\d+ self=\d key=(?!%d )' % key, text, re.M), text[-2000:]
        samples = [(int(e), float(t), float(i)) for e, t, i in re.findall(
            r'^EQUIPMENT_GLOW_SAMPLE entity=(\d+) key=%d t=([0-9.e+-]+) intensity=([0-9.e+-]+)$' % key, text, re.M)]
        assert samples and all(abs(i - expected(t)) < 1e-3 for _, t, i in samples), samples
        phases = {('rise' if c < 1 else 'hold' if c <= 3 else 'fall' if c < 5 else 'off')
                  for e, t, _ in samples if e != other for c in [math.fmod(t, 5.5)]}
        assert {'rise', 'hold', 'fall'} <= phases, (phases, samples)
        print(f"PASS Moradon client draws the 2233 equipment glow on the {case['label']} (key {key}) of itself and "
              f"of the other player, ends the other's on its unequip and starts it again on its re-equip; "
              f"{len(samples)} intensity samples follow 0056ea30's pulse through {sorted(phases)}", flush=True)
        pathlib.Path(config, 'n3e').mkdir()
        pathlib.Path(config, 'n3e', 'Option.ini').write_text('[Addition2233]\nEquipmentGlow=0\n')
        quiet = client(case, work / 'glow-off.ppm', config, b)
        assert 'EQUIPMENT_GLOW ' not in quiet and 'off by Option.ini [Addition2233] EquipmentGlow=0' in quiet, \
            quiet[-1500:]
    captures = {}
    for name, text_of in (('on', text), ('off', quiet)):
        made = re.findall(r'^EQUIPMENT_GLOW_CAPTURE at=([0-9.]+) drawn=[0-9.e+-]+ path=(.+)$', text_of, re.M)
        assert [float(a) for a, _ in made] == [PEAK, TROUGH], (name, made)
        captures[name] = [pathlib.Path(p) for _, p in made]
    if case['name'] == 'shield':
        peak, trough, off = warm(captures['on'][0]), warm(captures['on'][1]), warm(captures['off'][0])
        # Two glowing shields at the peak (the local player's and the other
        # player's), less glow at the trough (2x alone), and none without the glow.
        lit = [g for g in peak if g[0] >= 40]
        assert len(lit) >= 2 and sum(g[0] for g in trough) < sum(g[0] for g in peak), (peak, trough)
        assert sum(g[0] for g in off) < 20, off
        # At the trough the pulse is 0: only the 2x modulate is left, which still
        # lifts the shields' brass past the warm threshold the plain shields never reach.
        assert sum(g[0] for g in trough) >= sum(g[0] for g in off) + 40, (trough, off)
        summary = (f'{len(lit)} glowing shields at the pulse peak {[g[0] for g in lit]} px, '
                   f'{sum(g[0] for g in trough)} px at the trough, {sum(g[0] for g in off)} px with '
                   f'[Addition2233] EquipmentGlow=0')
    else:
        # Each player's blade, in the box the client drew it in: brighter than
        # the option off at the same second, both at the peak (emissive 1 at
        # 2x) and at the trough (the 2x modulate alone), and brighter at the
        # peak than at the trough (the pulse).
        where = boxes(text, other)
        measured = {who: dict(peak=lit_in(captures['on'][0], captures['off'][0], where[PEAK, who]),
                              trough=lit_in(captures['on'][1], captures['off'][1], where[TROUGH, who]),
                              pulse=lit_in(captures['on'][0], captures['on'][1], where[PEAK, who]))
                    for who in ('self', 'other')}
        assert all(m[k] >= NEEDED[k] for m in measured.values() for k in NEEDED), (measured, where)
        lit = [(0, *where[PEAK, who]) for who in ('self', 'other')]
        summary = ('the Durandal blades of the local and the other player, net pixels %d levels brighter in their '
                   'boxes %s and %s: peak over the option off %d and %d, trough (2x alone) over the option off %d '
                   'and %d, peak over trough %d and %d' % (
                       LEVELS, where[PEAK, 'self'], where[PEAK, 'other'], measured['self']['peak'],
                       measured['other']['peak'], measured['self']['trough'], measured['other']['trough'],
                       measured['self']['pulse'], measured['other']['pulse']))
    for ppm in (*captures['on'], *captures['off']):
        w, h, pixels = npc_looks_live.read_ppm(ppm)
        png(ppm.with_suffix('.png'), w, h, [pixels[y * w * 3:(y + 1) * w * 3] for y in range(h)])
    # A 3x crop around the two items: glow at the peak, at the trough, and off.
    x0, y0 = max(0, min(g[1] for g in lit[:2]) - 60), max(0, min(g[2] for g in lit[:2]) - 60)
    x1, y1 = min(w, max(g[3] for g in lit[:2]) + 60), min(h, max(g[4] for g in lit[:2]) + 60)
    sources = [npc_looks_live.read_ppm(p)[2] for p in (captures['on'][0], captures['on'][1], captures['off'][0])]
    rows = []
    for y in range(y0, y1):
        row = b''
        for src in sources:
            row += b''.join(bytes(src[(y * w + x) * 3:(y * w + x) * 3 + 3]) * 3 for x in range(x0, x1))
        rows += [row] * 3
    crop = work / 'glow-crop-peak-trough-off.png'
    png(crop, (x1 - x0) * 9, (y1 - y0) * 3, rows)
    print(f"PASS Moradon equipment glow graphical ({case['label']}, key {key}): {summary}; one view in every "
          f"capture run ({VIEW.summary()}); "
          f"{captures['on'][0]}, {captures['on'][1]}, {captures['off'][0]}, {captures['off'][1]}, {crop}", flush=True)


sx, sz = recipe['gameplay']['spawn_x'], recipe['gameplay']['spawn_z']
a, b = peer('explorer'), peer('companion')
mine, held = {}, {}
for index, case in enumerate(CASES):
    if index:
        # The previous case's item back to the bag first, on both accounts (the
        # two-hander blocks the left hand).
        last = CASES[index - 1]
        a = peer('explorer', create=False)
        unequip(a, last, bag(a), mine['at'])
        held['s'] = unequip(b, last, held['s'], held['at'])
    mine['s'], mine['at'] = equip(a, case)
    a.logout()
    held['s'], held['at'] = equip(b, case, held.get('s'))
    if not index:
        # Ahead of the camera's opening view (towards -z), else the first open side.
        for dx, dz in ((0, -2.5), (2.5, 0), (-2.5, 0), (0, 2.5)):
            if walk(b, sx + dx, sz + dz):
                break
    print(f"PASS two Moradon accounts equip the {case['label']} (2145 item {case['ko']}) over the wire and carry "
          f"appearance key {case['key']}", flush=True)
    if os.environ.get('N3E_GRAPHICAL') == '1':
        graphical(case, b, held)
# The server's inventory policy is the glow package's inventory.bin, the one
# that names the two-hander Durandal: every bag it keeps records the policy's
# definition, the SHA-256 of that file (server/src/inventory.rs Policy::load)
# chained with each bag policy file the package carries (server/src/content.rs:
# h = SHA-256(h || SHA-256(file)) for equipment, stats, wear, storage and
# storage-auth, in that order).


def bag_definition():
    h = hashlib.sha256(inventory).digest()
    for name in ('equipment.bin', 'stats.bin', 'wear.bin', 'storage.bin', 'storage-auth.bin'):
        if (package / name).is_file():
            h = hashlib.sha256(h + hashlib.sha256((package / name).read_bytes()).digest()).digest()
    return h.hex()


query = ("SELECT DISTINCT encode(definition, 'hex') FROM character_bags b JOIN characters c ON c.id = b.character_id "
         "JOIN accounts a ON a.id = c.account_id WHERE b.realm = '%s' AND a.name IN ('%s', '%s');"
         % (state['realm'], accounts['explorer'][0], accounts['companion'][0]))
definitions = subprocess.run(['docker', 'compose', '-p', moradon_stack.PROJECT, 'exec', '-T', 'postgres', 'psql', '-U',
                              'n3e', '-d', 'n3e', '-At', '-v', 'ON_ERROR_STOP=1', '-c', query], env=env, text=True,
                             capture_output=True, check=True).stdout.split()
assert definitions == [bag_definition()], (definitions, bag_definition())
print('PASS the glow package names the two-hander Durandal: inventory.bin labels demo:item/twohand "Durandal" '
      '(the server keeps both accounts\' bags under that file\'s definition %s), and its icon map draws %s '
      '(1298 Item_Org 126310000)' % (definitions[0][:12], DURANDAL_ICON), flush=True)


def icon_texels(path):
    """The icon's RGBA texels as the HUD decodes them, from the 1298 client data
    the package was cooked from (hash-checked against the cook's report)."""
    client = root / 'assets/ko/UI'
    found = [f for f in client.iterdir() if f.name.lower() == pathlib.PurePosixPath(path).name.lower()]
    assert len(found) == 1, (path, found)
    data = found[0].read_bytes()
    if path in [x['path'] for x in icon_rows.values()]:
        assert hashlib.sha256(data).hexdigest() == next(x['sha256'] for x in icon_rows.values() if x['path'] == path)
    return ko_hud.texture(data)


def icon_distance(capture, rect, texels):
    """Mean absolute RGB difference between the slot's screen pixels and the
    icon's opaque texels it shows (UV 0..45/64 across the slot, 004c1430),
    nearest texel, 2 px in from the slot's edges."""
    w, h, pixels = npc_looks_live.read_ppm(capture)
    tw, th, rgba = texels
    x0, y0, x1, y1 = rect
    total = count = 0
    for y in range(math.ceil(y0) + 2, math.floor(y1) - 2):
        for x in range(math.ceil(x0) + 2, math.floor(x1) - 2):
            u = min(44, int((x + .5 - x0) / (x1 - x0) * 45))
            v = min(44, int((y + .5 - y0) / (y1 - y0) * 45))
            t = (v * tw + u) * 4
            if rgba[t + 3] < 255:
                continue
            i = (y * w + x) * 3
            total += sum(abs(pixels[i + c] - rgba[t + c]) for c in range(3)) / 3
            count += 1
    assert count >= 200, (count, rect)
    return total / count, count


def inventory_view(where):
    """The client's inventory with the two-hander in the first account's gear
    (its right hand, the inventory window's equipment slot) or in its bag: the slot draws
    Durandal's icon and its tooltip names Durandal."""
    work = root / 'build/pq321/moradon/bag'
    work.mkdir(parents=True, exist_ok=True)
    capture = work / ('durandal-' + where)
    account, password = accounts['explorer']
    with tempfile.TemporaryDirectory(dir=root / 'build') as config:
        proc = subprocess.run(
            ['build/client/n3e-test-client', str(package), '--connect', 'localhost:' + str(state['port']), '--ca',
             'deploy/local/ca.pem', '--auto-login', '--fixed-window', '1280x1024', '--world-smoke', '60',
             '--capture', str(capture)],
            env={**env, 'N3E_TEST_ACCOUNT': account, 'N3E_TEST_PASSWORD': password, 'N3E_TEST_ITEM_TOOLTIP': 'twohand',
                 'N3E_TEST_ITEMS': 'twohand=demo:item/twohand', 'XDG_CONFIG_HOME': config},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
    text = proc.stdout
    capture.with_suffix('.log').write_text(text)
    assert proc.returncode == 0, (proc.returncode, text[-2000:])
    slot = re.findall(r'^ITEM_SLOT key=(%s:\d+) item=demo:item/twohand icon=1 rect=([0-9.e+-]+),([0-9.e+-]+),'
                      r'([0-9.e+-]+),([0-9.e+-]+)$' % where, text, re.M)
    assert len(slot) == 1, text[-2000:]
    key, rect = slot[0][0], tuple(float(v) for v in slot[0][1:])
    assert where == 'bag' or key == 'gear:%d' % RIGHT, key
    rows = re.findall(r'^ITEM_TOOLTIP key=%s row=(\d+) text=(.*)$' % re.escape(key), text, re.M)
    assert rows and rows[0] == ('0', 'Durandal'), rows
    assert not any('Two hand blade' in t for _, t in rows), rows
    shots = {name: pathlib.Path(f'{capture}.item-{name}.ppm') for name in ('slot', 'tooltip')}
    assert all(s.stat().st_size > 0 for s in shots.values()), shots
    durandal, count = icon_distance(shots['slot'], rect, icon_texels(DURANDAL_ICON))
    twohand, _ = icon_distance(shots['slot'], rect, icon_texels(TWOHAND_ICON))
    # The slot shows Durandal's texels, not the Two-Handed Sword's.
    assert durandal < 16 and twohand > 2 * durandal, (durandal, twohand, count, rect)
    for ppm in shots.values():
        w, h, pixels = npc_looks_live.read_ppm(ppm)
        png(ppm.with_suffix('.png'), w, h, [pixels[y * w * 3:(y + 1) * w * 3] for y in range(h)])
    print(f"PASS Moradon client {'equipment slot' if where == 'gear' else 'bag'} shows the two-hander as Durandal: "
          f"{key} at {rect} draws Durandal's icon (mean RGB difference {durandal:.1f} over {count} opaque texels, "
          f"the Two-Handed Sword's {twohand:.1f}) and its tooltip reads {[t for _, t in rows]}; "
          f"{shots['slot'].with_suffix('.png')}, {shots['tooltip'].with_suffix('.png')}", flush=True)


# PQ-316 (D-185): the same package carries Moradon's 2233 HDR bloom and tone
# map (2145 hdr.n3pp row 210), drawn only with Option.ini [Addition2233] HDR=1.
HDR = provenance['hdr_2233']
assert HDR['zone_key'] == 210 and HDR['row'] == 'kind 2' and HDR['rows'] == 55, HDR
assert recipe['postprocess'] == HDR['postprocess'], (recipe.get('postprocess'), HDR)
assert all(abs(HDR['postprocess'][k] - v) < 1e-5 for k, v in dict(
    threshold=.367, bloom=.7, exposure=.1, saturation=1.0, lift=.65, adapt_rate=.3, blur_variance=1.0).items()), HDR
assert (package / 'postprocess.bin').read_bytes()[:4] == b'N3PF'
HDR_STAGES = 420  # a frame of the world smoke after the login (about 7 s at 60 Hz)


def hdr(b):
    """The Moradon scene with the post-process on and at its default (off):
    the on client's chain equals its references on sampled pixels, adapts
    frame by frame at 0.3 per second, and its capture differs from the off
    client's at the same second of the local player's clock."""
    import postprocess_live as pl
    work = root / 'build/pq316/moradon'
    work.mkdir(parents=True, exist_ok=True)
    case = CASES[1]
    with tempfile.TemporaryDirectory(dir=root / 'build') as config:
        pathlib.Path(config, 'n3e').mkdir()
        pathlib.Path(config, 'n3e', 'Option.ini').write_text('[Addition2233]\nHDR=1\n')
        on = client(case, work / 'hdr-on.ppm', config, b, extra={
            'N3E_TEST_POSTPROCESS': '1', 'N3E_TEST_POSTPROCESS_STAGES': str(HDR_STAGES)})
    with tempfile.TemporaryDirectory(dir=root / 'build') as config:
        off = client(case, work / 'hdr-off.ppm', config, b, extra={'N3E_TEST_POSTPROCESS': '1'})
    assert 'HDR bloom: a 2233/2145 addition (N3PF), on' in on, on[:2000]
    assert 'HDR bloom: a 2233/2145 addition (N3PF), off; Option.ini [Addition2233] HDR=1 turns it on' in off
    assert 'POSTPROCESS ' not in off
    f = pl.frames(on)
    worst = 0.0
    for n in sorted(f):
        if n - 1 in f:
            step = .3 * f[n]['dt']
            for i in range(3):
                a, m, prev = f[n]['adapted'][i], f[n]['measured'][i], f[n - 1]['adapted'][i]
                want = prev + (-step if m <= prev else step) if step <= abs(prev - m) else m
                worst = max(worst, abs(a - want))
    assert f[min(f)]['read'] == 'sync' and 'async' in {x['read'] for x in f.values()} and worst < 2e-5, worst
    images = pl.stages(on, HDR_STAGES)
    s = dict(HDR['postprocess'])
    assert f[HDR_STAGES]['read'] == 'sync', f[HDR_STAGES]
    reduced, _ = pl.check_reduction(images['scene'], f[HDR_STAGES]['measured'], 'moradon')
    report = pl.check_chain(images, f[HDR_STAGES]['used'], 'moradon', s=s, stride=7)
    shots = {}
    for name, text in (('on', on), ('off', off)):
        made = re.findall(r'^EQUIPMENT_GLOW_CAPTURE at=([0-9.]+) drawn=[0-9.e+-]+ path=(.+)$', text, re.M)
        assert [float(a) for a, _ in made] == [PEAK, TROUGH], (name, made)
        shots[name] = pathlib.Path(made[0][1])
    a_img, b_img = pl.Image(shots['on']), pl.Image(shots['off'])
    changed = sum(1 for x, y in zip(a_img.rgb, b_img.rgb) if max(abs(p - q) for p, q in zip(x, y)) > 8)
    mean = lambda img: sum(map(pl.luminance, img.rgb)) / len(img.rgb)  # noqa: E731
    assert changed > len(a_img.rgb) // 4, changed
    for ppm in (shots['on'], shots['off'], *(work / ('hdr-on.ppm.stage-%d-%s.ppm' % (HDR_STAGES, k)) for k in ('bloom', 'final'))):
        w, h, pixels = npc_looks_live.read_ppm(ppm)
        png(ppm.with_suffix('.png'), w, h, [pixels[y * w * 3:(y + 1) * w * 3] for y in range(h)])
    print(f"PASS Moradon 2233 HDR bloom graphical: hdr.n3pp row 210 (threshold 0.367, bloom 0.7, exposure 0.1, "
          f"saturation 1.0, lift 0.65); every frame adapts at 0.3/s (worst {worst:.1e}); the read-back {reduced} and "
          f"the chain equal their references (stages on sampled pixels) {report} (used average and maximum {f[HDR_STAGES]['used']}); at "
          f"{PEAK} s {changed} of {len(a_img.rgb)} pixels differ from HDR off (mean luminance "
          f"{mean(a_img):.1f} on, {mean(b_img):.1f} off); {shots['on']}, {shots['off']}", flush=True)


if os.environ.get('N3E_GRAPHICAL') == '1':
    hdr(b)
drain(b)
b.logout()
if os.environ.get('N3E_GRAPHICAL') == '1':
    # The Durandal case left the two-hander in the first account's right hand.
    inventory_view('gear')
    a = peer('explorer', create=False)
    unequip(a, CASES[1], bag(a), mine['at'])
    a.logout()
    inventory_view('bag')
