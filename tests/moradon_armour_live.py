"""The 2145 Krowaz Assassin armour in Moradon's glow package (PQ-319, PQ-350),
against the prepared Moradon glow stack: a 2233/2145 addition (KO 1298 has none).

The package is the Moradon feature cook with --glow-2233
(packages/moradon-glow2233). games/moradon/armour-2233.json gives it the KO
race and class of its one character profile (race 2, the male Tuarek the
player model is; class 108, a Karus rogue class), four equipment slots (head,
lower body, hands, feet: the inventory window's areas 1, 10, 12 and 13) and
the five Krowaz Assassin parts on both of KO 2145's upgrade paths (PQ-346):
the normal +10 (248001020-248005020: Item_Ext tables 13-17 key 20, attribute
5, so 2233's 0056ea30 draws no glow) and the reverse +1 and +30
(258001001-258005001 and 258001030-258005030: tables 37-41 keys 1 and 30,
attribute 11, column 45 1 and 30: a pulse at MODULATE and a steady light at
MODULATE2X). tools/assetc/ko_armour_2145.py names each part's artwork as
2233's 009b3fc0 does (the model + race x 1000: Item/2_0802_<part>0_0.n3cpart,
the same on all three grades) and draws it on the part slot 009b3fc0 gives
(0, 1, 5, 3, 4), and names each item as 2233's tooltip (005aa8e0) does on its
first two lines: "Krowaz Assassin Upper Garment(+10)" and its kind, "(Set
item)" or "(Reverse set item)" (the set's need-race byte 124), the name its
label and the kind line its N3IH head line, both in the set's colour (PQ-354:
d20000 for the normal +10, ff83a6 for the reverse grades). The normal line
(tables 13-17) has no attribute 11 or 12 row at all; this suite reads both
lines' tables to say so.

Two fresh accounts wear whole sets over the wire; the server refuses a part in
another part's slot. With N3E_GRAPHICAL=1 the test client logs in as the first
(wearing the reverse +1 set) while the second (the reverse +30 set) stands
beside the spawn: the client must draw all five parts with the 2145 artwork
(each key's drawn triangles one of the cooked 2145 skin's levels) and their
glow on both players (EQUIPMENT_GLOW: pulse at 1x on the first, steady at 2x on
the second), the first's sampled intensities must follow 0056ea30's curve and
the second's stay at 1, the other player's helmet glow must end on its unequip
and start again on the re-equip, and in captures each part's box must be
brighter than with Option.ini [Addition2233] EquipmentGlow=0: the reverse +1's
at the pulse peak and not at the trough, the reverse +30's at both. Since
PQ-348 each part also draws with its own KO part render state (N3D3: blend
src_alpha / one_minus_src_alpha, both faces, alpha reference 0, as 1298's
00412570 and 0043ade0 draw an equipped part): the client reports it for every
key on both players, and the helmet's and the lower garment's boxes, whose
textures have cut-out texels, change against the next frame drawn with the
state ignored (N3E_TEST_PART_STATES=compare) by twice what the frame after
that, drawn again, changes them, and a margin more. The inventory window draws
each reverse +1 part in its own equipment slot with its 2145 icon
(UI/ItemIcon_2_4800_<part>0_0, the Item_Org icon, from the player's UI pack)
and names it. Both accounts then wear the normal +10 set: the client draws it
on both with its render state and no glow (no EQUIPMENT_GLOW for its keys,
and each part's box no brighter with the glow option on than the same
artwork with it off), and names its upper garment in the inventory. A capture
with the set taken off shows the default body there instead. Captures stay
under build/pq319/moradon (KO artwork; never committed). No user character is
touched.
"""
import json
import math
import os
import pathlib
import re
import secrets
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
import tooltip_head  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools/assetc'))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools/ko-reference'))
import ko_character  # noqa: E402  (the 1298 part readers, on the 2145 bytes read here)
import ko_glow_2233  # noqa: E402  (the pinned 2145 install and its manifest-checked tables)
import pack_2145  # noqa: E402

root = pathlib.Path(__file__).resolve().parents[1]
os.chdir(root)
state = moradon_stack.state()
package = (moradon_stack.WORK / 'packages/moradon-glow2233').resolve()
assert state['release'] == (package / 'release.sha256').read_text().strip(), 'the stack must serve the glow package'
recipe = json.loads((package / 'recipe.json').read_text())['manifest']
provenance = json.loads((moradon_stack.WORK / 'ko-moradon-glow2233/provenance.json').read_text())
armour = provenance['armour_2145']
assert armour['character'] == {'race': 2, 'class': 108}, armour['character']

# What 2233 draws for each part on race 2 / class 108 (009b3fc0, 0092fd30):
# (part, normal Item_Ext table, reverse table, part slot, inventory area, slot name, Item_Org name, artwork).
PARTS = [
    ('upper', 13, 37, 0, 4, 'Upper body', 'Krowaz Assassin Upper Garment', 1),
    ('lower', 14, 38, 1, 10, 'Lower body', 'Krowaz Assassin Lower Garment', 2),
    ('helmet', 15, 39, 5, 1, 'Head', 'Krowaz Assassin Helmet', 3),
    ('gauntlets', 16, 40, 3, 12, 'Hands', 'Krowaz Assassin Gauntlets', 4),
    ('boots', 17, 41, 4, 13, 'Feet', 'Krowaz Assassin Boots', 5)]
# PQ-346 / PQ-350: the grades carried, (Item_Org base, Item_Ext key, attribute,
# column 45, 0056ea30's glow (wave, modulate) or None, 005aa8e0's kind line);
# PQ-354: and the set's head colour (005aacc4 / 005aaffb: +0x154 ff83a6 for
# attribute 11, else +0x138 d20000, 005a9160's constants).
GRADES = {'normal10': (248000000, 20, 5, 0, None, '(Set item)', 0xd20000),
          'reverse1': (258000000, 1, 11, 1, ('pulse', 1), '(Reverse set item)', 0xff83a6),
          'reverse30': (258000000, 30, 11, 30, ('steady', 2), '(Reverse set item)', 0xff83a6)}
SUFFIX = {'normal10': '(+10)', 'reverse1': '(+1)', 'reverse30': '(+30)'}
# item: dict(part, grade, number, table, part slot, area, slot, label, artwork
# n, head: (name colour, [(kind line, colour)])).
ITEM = {}
for grade, (base, key, *_, kind, colour) in GRADES.items():
    for n, (part, normal, reverse, slot_part, area, slot, name, art) in enumerate(PARTS, 1):
        ITEM['demo:item/krowaz_%s_%s' % (part, grade)] = dict(
            part=part, grade=grade, number=base + n * 1000 + key, table=normal if grade == 'normal10' else reverse,
            part_slot=slot_part, area=area, slot=slot, label='%s%s' % (name, SUFFIX[grade]), n=art,
            head=(colour, [(kind, colour)]))
SET = {g: ['demo:item/krowaz_%s_%s' % (p[0], g) for p in PARTS] for g in GRADES}
SLOTS = ['Right hand', 'Left hand', 'Right ring', 'Left ring', 'Upper body', 'Head', 'Lower body', 'Hands', 'Feet']
assert armour['slots'] == SLOTS[5:] and armour['areas'] == {'6': 0, '8': 1, '9': 2, '11': 3, '4': 4, '1': 5,
                                                             '10': 6, '12': 7, '13': 8}, armour
KEYS = {i: 1 + [r['item'] for r in recipe['appearance']].index(i) for i in ITEM}
SLOT_OF = {i: SLOTS.index(x['slot']) for i, x in ITEM.items()}
assert [(r['item'], r['slot']) for r in recipe['appearance'] if r['item'] in KEYS] == [
    (i, SLOT_OF[i]) for g in GRADES for i in SET[g]], recipe['appearance']
for item, x in ITEM.items():
    base, key, attribute, c45, glow, _, _ = GRADES[x['grade']]
    got = armour['items'][item]
    assert (got['item_2145'], got['extension_table'], got['extension_key'], got['attribute'], got['column_45'],
            got['part'], got['area'], got['slot'], got['name'], got['artwork'], got['kind'], got['need_class'],
            got['need_race'], got['glow']) == (
        x['number'], x['table'], key, attribute, c45, x['part_slot'], x['area'], x['slot'], x['label'],
        'Item/2_0802_%d0_0.n3cpart' % x['n'], 220, 8, 124,
        None if glow is None else dict(wave=int(glow[0] == 'pulse'), modulate=glow[1])), (item, got)
    assert (got['head']['name_color'], [(h['text'], h['color']) for h in got['head']['lines']]) == x['head'], (item, got)
# 0056ea30: a record for each reverse part (pulse 1x, steady 2x), none for a normal one.
glows = {g['item']: g for g in provenance['glow_2233']['glow'] if 'armour_2145' in g}
assert [(i, g['key'], g['glow_2145_item'], g['wave'], g['modulate'], g['armour_2145'], g['parts'])
        for i, g in glows.items()] == [
    (i, KEYS[i], x['number'], *GRADES[x['grade']][4], 'Item/2_0802_%d0_0.n3cpart' % x['n'], [x['part_slot']])
    for i, x in ITEM.items() if x['grade'] != 'normal10'], glows
assert len(provenance['glow_2233']['glow']) == 15, provenance['glow_2233']['glow']
drawn = {r['item']: r for r in provenance['render_detail']['appearances'] if r.get('armour_2145')}
icons = {x['item']: x for x in provenance['glow_2233']['presentation']['armour_icons']['items']}
assert all(icons[i]['path'] == 'UI/ItemIcon_2_4800_%d0_0.dxt' % x['n'] for i, x in ITEM.items()), icons

# The 2145 tables, read here: the normal line has no glow row and its row 20
# is attribute 5; the reverse line's rows 1 and 30 are attribute 11, column 45 1 and 30.
install = ko_glow_2233.Install(ko_glow_2233.INSTALL)
for _, normal, reverse, *_ in PARTS:
    _, rows = install.table(ko_glow_2233.EXT.format(normal))
    assert not [r for r in rows.values() if r[7] in (11, 12)], normal
    assert (rows[20][7], rows[20][44], rows[20][2]) == (5, 0, 0), (normal, rows[20][:3])
    _, rows = install.table(ko_glow_2233.EXT.format(reverse))
    assert [(rows[k][7], rows[k][44], rows[k][2]) for k in (1, 30)] == [(11, 1, 0), (11, 30, 0)], reverse
print('PASS the 2145 tables: Krowaz Assassin 248001000-248005000 (Item_Ext 13-17) have no attribute 11 or 12 row '
      '(no glow) and row 20 (the normal +10) is attribute 5; 258001000-258005000 (Item_Ext 37-41) rows 1 and 30 '
      'are attribute 11, column 45 = 1 and 30 (reverse +1 and +30: a pulse at 1x, a steady light at 2x); the '
      'package carries 15 glow records, the ten reverse parts\' and none for the normal +10', flush=True)

# The artwork, read here from the player's 2145 Item pack: each part's skin
# levels are the triangles the package cooked for its keys (all three grades).
item_pack = pack_2145.Pack(ko_glow_2233.INSTALL / 'client/Item/item.hdr')
TRIANGLES = {}
for part, *_, n in PARTS:
    data = ko_character.part(item_pack.read('2_0802_%d0_0.n3cpart' % n))
    assert data['skin'].lower() == 'item\\2_0802_%d0_0.n3cskins' % n, data
    _, skins = ko_character.skins(item_pack.read(data['skin'].split('\\', 1)[1]))
    TRIANGLES[part] = [len(s['indices']) // 3 for s in skins]
for item, x in ITEM.items():
    assert drawn[item]['triangles'] == TRIANGLES[x['part']] and drawn[item]['parts'] == [x['part_slot']], (
        item, drawn[item], TRIANGLES[x['part']])
print('PASS the glow package draws the Krowaz Assassin parts of all three grades with their race-2 2145 artwork %s '
      'on part slots %s, keys %s (2233 009b3fc0 with race 2, class 108)'
      % (sorted({drawn[i]['source'] for i in ITEM}), [p[3] for p in PARTS], [KEYS[i] for i in ITEM]), flush=True)


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


def slot_names(data):
    """The equipment slot names of an N3Q1 equipment policy (server/src/equipment.rs)."""
    assert data[:4] == b'N3Q1', data[:4]
    n, at, names = struct.unpack_from('<I', data, 32)[0], 36, []
    for _ in range(n):
        size = struct.unpack_from('<I', data, at)[0]
        names.append(data[at + 4:at + 4 + size].decode('ascii'))
        at += 4 + size
    return names


inventory = labels((package / 'inventory.bin').read_bytes())
assert all(inventory[i] == x['label'] for i, x in ITEM.items()), inventory
# PQ-354 (D-194): the package's N3IH heads carry each part's colour and kind
# line, and 2233's token.
import item_heads  # noqa: E402
token, cooked_heads = item_heads.parse((package / 'item-heads.bin').read_bytes(), recipe['game_id'], set(inventory))
assert token == '<selfname>' and all(cooked_heads[i] == x['head'] for i, x in ITEM.items()), (token, cooked_heads)
assert slot_names((package / 'equipment.bin').read_bytes()) == SLOTS, slot_names((package / 'equipment.bin').read_bytes())

env = {**os.environ, 'N3E_IMAGE': moradon_stack.IMAGE, 'N3E_PACKAGE_PATH': str(package), 'N3E_PORT': str(state['port']),
       'N3E_REALM': state['realm']}
PEAK, TROUGH = 7.5, 10.75  # seconds of the local player's clock: the pulse held at 1, then at 0
LEVELS, PAD = 30, 3
accounts = {}
for role in ('explorer', 'companion'):
    account = 'armour' + role[:4] + secrets.token_hex(5)
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


def request(p, op, source, destination, s):
    """One bag operation; (status, the reply's state)."""
    time.sleep(.22)  # inside the shared inventory request budget
    serial[0] += 1
    records = s[6] if op == 6 else s[5]
    p.send(32, integer(1, op) + blob(2, f'pq319-{secrets.token_hex(4)}-{serial[0]}') + integer(3, first(s, 1))
           + integer(4, source) + integer(5, destination) + integer(6, first(fields(records[source]), 1)))
    d = wait(p, 33)
    return first(d, 2), first(d, 3)


def bag(p):
    time.sleep(.22)
    p.send(32, b'')
    return fields(first(wait(p, 33, lambda d: first(d, 2) == b'ok'), 3))


def keys(p):
    return list(first(p.entities.get(p.id, {}), 20, b''))


def worn(items):
    """The appearance keys the server projects for `items` worn: slot order."""
    return [KEYS[i] for i in sorted(items, key=lambda i: SLOT_OF[i])]


def wear(p, items, s=None, result=None):
    """Equip each of `items` from the bag into its slot, then wait for the
    keys of `result` (default `items`) worn; (state, {item: bag slot})."""
    s = bag(p) if s is None else s
    came = {}
    for item in items:
        at = next(i for i, r in enumerate(s[5]) if first(fields(r), 2) == item.encode())
        status, reply = request(p, 5, at, SLOT_OF[item], s)
        assert status == b'committed', (item, status)
        s, came[item] = fields(reply), at
    wait(p, 10, lambda _: keys(p) == worn(items if result is None else result))
    return s, came


def strip(p, items, came, s):
    """Return each of `items` to the bag slot it came from; the new state."""
    for item in items:
        status, reply = request(p, 6, SLOT_OF[item], came[item], s)
        assert status == b'committed', (item, status)
        s = fields(reply)
    return s


def drain(p):
    import select
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


a, b = peer('explorer'), peer('companion')
# The server validates each equip against the package's slots: the helmet in
# the upper body slot is refused and the bag is unchanged.
s = bag(b)
helmet = next(i for i, r in enumerate(s[5]) if first(fields(r), 2) == b'demo:item/krowaz_helmet_normal10')
status, _ = request(b, 5, helmet, SLOT_OF['demo:item/krowaz_upper_normal10'], s)
after = bag(b)
assert status == b'incompatible_slot' and after[6] == s[6] and after[5] == s[5], status
print('PASS the server refuses the Krowaz Assassin Helmet in the upper body slot (%s); the bag is unchanged'
      % status.decode(), flush=True)
# The first account wears the reverse +1 set, the second the reverse +30 set.
MINE, THEIRS = SET['reverse1'], SET['reverse30']
mine, came_a = wear(a, MINE)
a.logout()
held = {}
held['s'], held['came'] = wear(b, THEIRS, s)
sx, sz = recipe['gameplay']['spawn_x'], recipe['gameplay']['spawn_z']
for dx, dz in ((0, -2.5), (2.5, 0), (-2.5, 0), (0, 2.5)):
    if walk(b, sx + dx, sz + dz):
        break
print('PASS two Moradon accounts wear the five Krowaz Assassin parts over the wire, each in its own slot %s: the '
      'reverse +1 set (keys %s) and the reverse +30 set (keys %s)'
      % ([SLOT_OF[i] for i in MINE], worn(MINE), worn(THEIRS)), flush=True)


def expected(t):
    """0056ea30 (2233): i = t to 1 s, held to 3 s, 1 - (t - 3) x 0.5 to 5 s, 0 to 5.5 s."""
    c = math.fmod(t, 5.5)
    return c if c <= 1 else 1 if c <= 3 else 1 - (c - 3) * .5 if c <= 5 else 0


def png(path, width, height, rows):
    raw = b''.join(b'\0' + bytes(r) for r in rows)
    chunk = lambda kind, data: (struct.pack('>I', len(data)) + kind + data  # noqa: E731
                                + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def to_png(ppm):
    w, h, pixels = npc_looks_live.read_ppm(ppm)
    png(ppm.with_suffix('.png'), w, h, [pixels[y * w * 3:(y + 1) * w * 3] for y in range(h)])
    return ppm.with_suffix('.png')


def lit_in(path, base, box, levels=LEVELS, exclude=()):
    """Pixels of `box` at least `levels` brighter in every channel than the same
    pixel of `base`, less those as much darker (the idle sway moves a few);
    pixels inside any box of `exclude` are not counted."""
    w, h, pixels = npc_looks_live.read_ppm(path)
    _, _, under = npc_looks_live.read_ppm(base)
    x0, y0, x1, y1 = box
    net = 0
    for y in range(max(0, y0), min(h, y1 + 1)):
        for x in range(max(0, x0), min(w, x1 + 1)):
            if any(e[0] <= x <= e[2] and e[1] <= y <= e[3] for e in exclude):
                continue
            i = (y * w + x) * 3
            net += all(pixels[i + c] >= under[i + c] + levels for c in range(3))
            net -= all(under[i + c] >= pixels[i + c] + levels for c in range(3))
    return net


def changed_in(path, base, box, levels=LEVELS):
    """Pixels of `box` that differ from `base` by `levels` or more in any channel."""
    w, h, pixels = npc_looks_live.read_ppm(path)
    _, _, under = npc_looks_live.read_ppm(base)
    x0, y0, x1, y1 = box
    return sum(1 for y in range(max(0, y0), min(h, y1 + 1)) for x in range(max(0, x0), min(w, x1 + 1))
               if max(abs(pixels[(y * w + x) * 3 + c] - under[(y * w + x) * 3 + c]) for c in range(3)) >= levels)


def boxes(text, other):
    """{(capture second, 'self' or 'other', part): the part's screen box, grown
    by PAD} (the client reports a box for a glowing key)."""
    found = {}
    for at, entity, me, key, x0, y0, x1, y1 in re.findall(
            r'^EQUIPMENT_GLOW_BOX at=([0-9.]+) entity=(\d+) self=(\d) key=(\d+) box=(-?\d+),(-?\d+),(-?\d+),(-?\d+)$',
            text, re.M):
        item = next((i for i, k in KEYS.items() if k == int(key)), None)
        if item is None:
            continue
        who = 'self' if me == '1' else 'other' if int(entity) == other else None
        part = ITEM[item]['part']
        assert who and (float(at), who, part) not in found, (at, entity, me, key)
        found[float(at), who, part] = (int(x0) - PAD, int(y0) - PAD, int(x1) + PAD, int(y1) + PAD)
    return found


def client(capture, config, steps=(), extra=None, smoke=20, whole=True):
    lines = []
    account, password = accounts['explorer']
    proc = subprocess.Popen(
        ['build/client/n3e-test-client', str(package), '--connect', 'localhost:' + str(state['port']), '--ca',
         'deploy/local/ca.pem', '--auto-login', '--fixed-window', '1280x1024', '--world-smoke', str(smoke),
         '--capture', str(capture)],
        env={**env, 'N3E_TEST_ACCOUNT': account, 'N3E_TEST_PASSWORD': password, 'XDG_CONFIG_HOME': config,
             **(extra or {})},
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
    assert proc.returncode == 0 and (not whole or capture.stat().st_size > 0), (proc.returncode, text[-1500:])
    assert not pending, ('steps not reached', len(pending), text[-1500:])
    return text


def glow_client(capture, config, steps=(), states='1'):
    """`states` 'compare' also captures, after each glow capture, the next
    frame with every key drawn as N3D2 draws it and the frame after that as
    drawn (PQ-348's comparison captures). Every glow run's captures share
    one view (PQ-355): the suite compares them across runs."""
    text = client(capture, config, steps, extra={'N3E_TEST_EQUIPMENT_GLOW': '1',
                                                 'N3E_TEST_EQUIPMENT_GLOW_CAPTURES': f'{PEAK},{TROUGH}',
                                                 'N3E_TEST_PART_STATES': states})
    VIEW.check(capture.name, text)
    return text


VIEW = capture_camera.SameView()


def part_states(text, other, drawn, mine, theirs):
    """PQ-348: every part key reports the part's own render state, on both
    players (the local player wearing `mine`, the other `theirs`): 00412570's
    blend (src_alpha / one_minus_src_alpha) and both faces, reference 0
    (0043ade0's alpha test), `drawn` 1 with it and 0 ignored."""
    found = {(e, k): (f, r, src, dst, d) for e, k, f, r, src, dst, d in re.findall(
        r'^PART_STATE entity=(\d+) self=\d key=(\d+) flags=(\d+) reference=([0-9.e+-]+) source=(\d+) '
        r'destination=(\d+) drawn=(\d) vertices=\d+$', text, re.M)}
    me = {e for e, k in found if e != str(other)}
    assert len(me) == 1, found
    for who, items in ((me.pop(), mine), (str(other), theirs)):
        for item in items:
            assert found.get((who, str(KEYS[item]))) == ('3', '0', '4', '5', drawn), (who, item, found)
    return found


def captures(text):
    made = re.findall(r'^EQUIPMENT_GLOW_CAPTURE at=([0-9.]+) drawn=[0-9.e+-]+ path=(.+)$', text, re.M)
    assert [float(t) for t, _ in made] == [PEAK, TROUGH], made
    return [pathlib.Path(p) for _, p in made]


def found(*patterns):
    return lambda text: all(re.search(p, text, re.M) for p in patterns)


def start(entity, me, item):
    """The client's first report of `item`'s glow on a player (its grade's wave and modulate)."""
    wave, modulate = GRADES[ITEM[item]['grade']][4]
    return r'^EQUIPMENT_GLOW entity=%s self=%d key=%d wave=%s modulate=%d color=1,1,1 vertices=(\d+)$' % (
        entity, me, KEYS[item], wave, modulate)


def body(where, w):
    """The box around a player's five parts at the peak capture."""
    return tuple(f(where[PEAK, w, p[0]][i] for p in PARTS) for i, f in enumerate((min, min, max, max)))


def graphical():
    """The reverse sets drawn and glowing on both players (the local reverse
    +1, the other's reverse +30), the other's helmet unequip and re-equip, the
    samples, and the captures against the option off."""
    other, helmet = b.id, 'demo:item/krowaz_helmet_reverse30'
    work = root / 'build/pq319/moradon'
    work.mkdir(parents=True, exist_ok=True)
    end = rf'^EQUIPMENT_GLOW_END entity={other} key={KEYS[helmet]}$'
    every = [start(r'\d+', 1, i) for i in MINE] + [start(other, 0, i) for i in THEIRS]

    def off():
        held['s'] = strip(b, [helmet], held['came'], held['s'])

    def on():
        held['s'], came = wear(b, [helmet], held['s'], THEIRS)
        held['came'].update(came)

    with tempfile.TemporaryDirectory(dir=root / 'build') as config:
        text = glow_client(work / 'armour-on.ppm', config, steps=[(found(*every), off), (found(end), on)])
        assert 'a 2233/2145 addition (N3E3), on' in text, text[:1500]
        for item in MINE + THEIRS:
            lines = re.findall(start(r'\d+', 1, item) if item in MINE else start(other, 0, item), text, re.M)
            assert len(lines) == (2 if item == helmet else 1), (item, lines, text[-2000:])
            # The drawn mesh is one of the 2145 skin's levels (3 vertices a triangle).
            assert all(int(v) % 3 == 0 and int(v) // 3 in TRIANGLES[ITEM[item]['part']] for v in lines), (
                item, lines)
        # No other Krowaz key glows: each player glows its own set only.
        lit_keys = {int(k) for k in re.findall(r'^EQUIPMENT_GLOW entity=\d+ self=\d key=(\d+) ', text, re.M)}
        assert lit_keys & set(KEYS.values()) == {KEYS[i] for i in MINE + THEIRS}, lit_keys
        assert len(re.findall(end, text, re.M)) == 1, text[-2000:]
        samples = [(int(e), int(k), float(t), float(i)) for e, k, t, i in re.findall(
            r'^EQUIPMENT_GLOW_SAMPLE entity=(\d+) key=(\d+) t=([0-9.e+-]+) intensity=([0-9.e+-]+)$', text, re.M)
            if int(k) in KEYS.values()]
        ours = [(t, i) for e, _, t, i in samples if e != other]
        theirs = [i for e, _, _, i in samples if e == other]
        assert ours and all(abs(i - expected(t)) < 1e-3 for t, i in ours), ours
        assert theirs and all(i == 1 for i in theirs), theirs
        phases = {('rise' if c < 1 else 'hold' if c <= 3 else 'fall' if c < 5 else 'off')
                  for t, _ in ours for c in [math.fmod(t, 5.5)]}
        assert {'rise', 'hold', 'fall'} <= phases, (phases, ours)
        print(f"PASS Moradon client draws the five Krowaz Assassin parts with their 2145 artwork and the 2233 "
              f"equipment glow on itself (reverse +1: pulse, 1x) and on the other player (reverse +30: steady, 2x), "
              f"ends the other's helmet glow on its unequip and starts it again on its re-equip; {len(ours)} "
              f"intensity samples follow 0056ea30's pulse through {sorted(phases)}, the other's {len(theirs)} stay "
              f"at 1", flush=True)
        pathlib.Path(config, 'n3e').mkdir()
        pathlib.Path(config, 'n3e', 'Option.ini').write_text('[Addition2233]\nEquipmentGlow=0\n')
        # PQ-348: with the next frame after each capture drawn as N3D2 draws
        # every key (culled, cut at 0.5, no blend) and the one after as drawn.
        quiet = glow_client(work / 'armour-glow-off.ppm', config, states='compare')
        assert 'EQUIPMENT_GLOW ' not in quiet and 'off by Option.ini [Addition2233] EquipmentGlow=0' in quiet, \
            quiet[-1500:]
    part_states(text, other, '1', MINE, THEIRS)
    part_states(quiet, other, '1', MINE, THEIRS)
    on, off = captures(text), captures(quiet)
    compared = re.findall(r'^PART_STATE_COMPARE at=([0-9.]+) mode=(ignored|again) path=(.+)$', quiet, re.M)
    assert [(float(t), m) for t, m, _ in compared] == [(PEAK, 'ignored'), (PEAK, 'again'), (TROUGH, 'ignored'),
                                                      (TROUGH, 'again')], compared
    ignored, control = [pathlib.Path(p) for *_, p in compared[0::2]], [pathlib.Path(p) for *_, p in compared[1::2]]
    where = boxes(text, other)
    names = [p[0] for p in PARTS]
    assert set(where) == {(t, w, n) for t in (PEAK, TROUGH) for w in ('self', 'other') for n in names}, sorted(where)
    # The other stands ahead of the camera, so some of its parts' boxes overlap
    # the local player's (its boots and gauntlets behind the local helmet;
    # PQ-350's first run counted the other's steady 2x in the local helmet's
    # box against the option off). So each comparison is one the other
    # player's light cannot pass:
    # - the local reverse +1 (pulse, 1x): each part's box brighter at the peak
    #   than at the trough of the same run (the other's steady light is the
    #   same at both and cancels), and, in each box clear of the other's, no
    #   brighter at the trough than the option off (intensity 0 at 1x is the
    #   option off; 2x would still light it);
    # - the other's reverse +30 (steady, 2x): each part's box brighter at the
    #   trough than the option off (the local pulse is 0 there), and its set,
    #   the local boxes left out, alike at the peak and the trough.
    def overlaps(p, q):
        return p[0] <= q[2] and q[0] <= p[2] and p[1] <= q[3] and q[1] <= p[3]
    mine_boxes = [where[t, 'self', n] for t in (PEAK, TROUGH) for n in names]
    clear = [n for n in names if not any(overlaps(where[TROUGH, 'self', n], where[TROUGH, 'other', m]) for m in names)]
    measured = {n: dict(pulse=lit_in(on[0], on[1], where[PEAK, 'self', n]),
                        trough=lit_in(on[1], off[1], where[TROUGH, 'self', n])) for n in names}
    steady = {n: lit_in(on[1], off[1], where[TROUGH, 'other', n]) for n in names}
    pulse = {'self': lit_in(on[0], on[1], body(where, 'self')),
             'other': lit_in(on[0], on[1], body(where, 'other'), exclude=mine_boxes)}
    assert all(measured[n]['pulse'] >= NEEDED['peak_1x'] for n in names), (measured, where)
    assert len(clear) >= 2 and all(measured[n]['trough'] < NEEDED['quiet'] for n in clear), (clear, measured)
    assert all(v >= NEEDED['peak'] for v in steady.values()), (steady, where)
    assert pulse['self'] >= NEEDED['pulse'] and abs(pulse['other']) < NEEDED['pulse'], (pulse, where)
    print('PASS Moradon Krowaz Assassin glow graphical: net pixels %d levels brighter in each part\'s box: the '
          'local reverse +1 (pulse 1x) at the peak than at the trough %s, at the trough than the option off (boxes '
          'clear of the other player\'s) %s; the other\'s reverse +30 (steady 2x) at the trough than the option off '
          '%s; over each player\'s set, peak over trough: %s; one view in every capture run (%s); %s'
          % (LEVELS, {n: m['pulse'] for n, m in measured.items()}, {n: measured[n]['trough'] for n in clear}, steady,
             pulse, VIEW.summary(), ', '.join(str(to_png(p)) for p in (*on, *off))), flush=True)
    # PQ-348: the parts drawn with their render state against the next frame,
    # the state ignored, and, as the control, the frame after that as drawn
    # (two frames of the idle sway against one), with the glow off.
    states = {(t, w, n): changed_in(off[i], ignored[i], where[t, w, n])
              for i, t in enumerate((PEAK, TROUGH)) for w in ('self', 'other') for n in names}
    noise = {(t, w, n): changed_in(off[i], control[i], where[t, w, n])
             for i, t in enumerate((PEAK, TROUGH)) for w in ('self', 'other') for n in names}
    # The helmet and the lower garment carry the cut-out texels: the helmet's
    # box, and the two boxes together, change by twice what the control frame
    # changes them and a margin more, on both players at both times.
    for t in (PEAK, TROUGH):
        for w in ('self', 'other'):
            assert states[t, w, 'helmet'] >= 2 * noise[t, w, 'helmet'] + 30, (t, w, states, noise)
            both = states[t, w, 'helmet'] + states[t, w, 'lower']
            assert both >= 2 * (noise[t, w, 'helmet'] + noise[t, w, 'lower']) + 60, (t, w, states, noise)
    short = lambda m: {f'{t} {w} {n}': v for (t, w, n), v in m.items()}  # noqa: E731
    print('PASS Moradon client draws the Krowaz Assassin parts with their part render state (blend src_alpha / '
          'one_minus_src_alpha, both faces, alpha reference 0) on both players: pixels %d levels different in each '
          'part\'s box from the next frame with the state ignored, at %s s and %s s: %s; from the frame after '
          'that, as drawn: %s; %s'
          % (LEVELS, PEAK, TROUGH, short(states), short(noise), ', '.join(str(to_png(p)) for p in ignored)),
          flush=True)
    return where, off


def normal(where, off):
    """Both players in the normal +10 set (attribute 5): drawn with its render
    state and no glow, each part's box no brighter with the glow option on
    than the same artwork with it off (the reverse sets' glow-off captures)."""
    other, work = b.id, root / 'build/pq319/moradon'
    with tempfile.TemporaryDirectory(dir=root / 'build') as config:
        text = glow_client(work / 'armour-normal.ppm', config)
    assert 'a 2233/2145 addition (N3E3), on' in text, text[:1500]
    assert not re.search(r'^EQUIPMENT_GLOW entity=\d+ self=\d key=(%s) ' % '|'.join(
        str(KEYS[i]) for i in SET['normal10']), text, re.M), text[-1500:]
    part_states(text, other, '1', SET['normal10'], SET['normal10'])
    shots = captures(text)
    names = [p[0] for p in PARTS]
    gain = {(t, w, n): lit_in(shots[i], off[i], where[t, w, n])
            for i, t in enumerate((PEAK, TROUGH)) for w in ('self', 'other') for n in names}
    assert all(v < NEEDED['quiet'] for v in gain.values()), gain
    print('PASS Moradon client draws the normal +10 Krowaz Assassin set (attribute 5) on itself and on the other '
          'player with its part render state and no glow (no EQUIPMENT_GLOW for its keys %s); net pixels %d levels '
          'brighter than the same artwork with the option off, per part box: %s; %s'
          % ([KEYS[i] for i in SET['normal10']], LEVELS, {f'{t} {w} {n}': v for (t, w, n), v in gain.items()},
             ', '.join(str(to_png(p)) for p in shots)), flush=True)
    return shots


# Net pixels a part's box must gain (peak, trough, peak_1x) and a player's
# whole set (pulse), and the most a box may gain without a glow (quiet). With
# the reverse +15 (a pulse at 2x) the far player's helmet gained 500 / 322 in
# the first make live-ko run (build/live-ko/failed/20261021-141927-3610278),
# the nearer parts thousands; a set's peak over its trough 2,206 or more; the
# idle sway alone moves about 40.
# With the reverse +1 (a pulse at 1x) on the near player and the reverse +30
# (steady 2x) on the far one, PQ-350's first runs: the near boots and lower
# garment gained 151 and 176 at the peak over the option off, the others 383
# to 1,305; the far player's parts 849 to 3,812 at the trough.
NEEDED = dict(peak=200, trough=100, pulse=300, peak_1x=80, quiet=100)


def icon_texels(n):
    """(width, height, RGBA) of UI/ItemIcon_2_4800_<n>0_0.dxt from the player's
    2145 UI pack, read here: a name, NTF\\x03, width, height, format 25
    (A1R5G5B5), no mipmaps, then one u16 per texel."""
    data = pack_2145.Pack(ko_glow_2233.INSTALL / 'client/UI/ui.hdr').read('itemicon_2_4800_%d0_0.dxt' % n)
    size = struct.unpack_from('<i', data, 0)[0]
    assert data[4 + size:8 + size] == b'NTF\x03', data[:16]
    w, h, fmt, mips = struct.unpack_from('<4i', data, 8 + size)
    raw = data[24 + size:]
    assert (fmt, mips, len(raw)) == (25, 0, w * h * 2), (fmt, mips, len(raw))
    out = bytearray()
    for (v,) in struct.iter_unpack('<H', raw):
        out += bytes((((v >> 10) & 31) * 255 // 31, ((v >> 5) & 31) * 255 // 31, (v & 31) * 255 // 31,
                      255 if v & 0x8000 else 0))
    return w, h, bytes(out)


def icon_distance(capture, rect, texels):
    """Mean absolute RGB difference between the slot's screen pixels and the
    icon's opaque texels (UV 0..45/64 across the slot, 004c1430), nearest
    texel, 2 px in from the slot's edges."""
    w, h, pixels = npc_looks_live.read_ppm(capture)
    tw, _, rgba = texels
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


def inventory_view(item, n, label):
    """The first account's inventory: the part in its own equipment slot, drawn
    with its 2145 icon and named as 2233's tooltip names it, its head (the name
    and the kind line) in the set's colour (PQ-354)."""
    work = root / 'build/pq319/moradon/gear'
    work.mkdir(parents=True, exist_ok=True)
    shot = work / item.split('/')[-1]
    with tempfile.TemporaryDirectory(dir=root / 'build') as config:
        text = client(shot, config, extra={'N3E_TEST_ITEM_TOOLTIP': 'part', 'N3E_TEST_ITEMS': 'part=' + item},
                      smoke=60, whole=False)
    slot = re.findall(r'^ITEM_SLOT key=(gear:\d+) item=%s icon=(\d) rect=([0-9.e+-]+),([0-9.e+-]+),([0-9.e+-]+),'
                      r'([0-9.e+-]+)$' % re.escape(item), text, re.M)
    assert len(slot) == 1, text[-2000:]
    key, icon, rect = slot[0][0], slot[0][1], tuple(float(v) for v in slot[0][2:])
    assert key == 'gear:%d' % SLOT_OF[item] and icon == '1', (key, icon)
    rows = re.findall(r'^ITEM_TOOLTIP key=%s row=(\d+) text=(.*)$' % re.escape(key), text, re.M)
    assert rows and rows[0] == ('0', label), rows
    shots = {name: pathlib.Path(f'{shot}.item-{name}.ppm') for name in ('slot', 'tooltip')}
    near, count = icon_distance(shots['slot'], rect, icon_texels(n))
    other = icon_distance(shots['slot'], rect, icon_texels(5 if n != 5 else 1))[0]
    assert near < 16 and other > 2 * near, (near, other, count, rect)
    colour, lines = ITEM[item]['head']
    head, _ = tooltip_head.check(text, key, shots['tooltip'], [(label, colour)] + lines, base=shots['slot'])
    print(f"PASS Moradon client equipment slot {key} ({SLOTS[SLOT_OF[item]]}, inventory area "
          f"{armour['items'][item]['area']}) draws {label} with its 2145 icon UI/ItemIcon_2_4800_{n}0_0.dxt (mean RGB "
          f"difference {near:.1f} over {count} texels, another part's icon {other:.1f}), tooltip "
          f"{[t for _, t in rows]}, its head drawn (row, colour, pixels of it, without the tooltip) {head}; {to_png(shots['slot'])}, "
          f"{to_png(shots['tooltip'])}", flush=True)


if os.environ.get('N3E_GRAPHICAL') == '1':
    where, glow_off = graphical()
    for item in MINE:
        inventory_view(item, ITEM[item]['n'], ITEM[item]['label'])
    # Both accounts change to the normal +10 set.
    held['s'] = strip(b, THEIRS, held['came'], held['s'])
    wait(b, 10, lambda _: keys(b) == [])
    held['s'], held['came'] = wear(b, SET['normal10'], held['s'])
    a = peer('explorer', create=False)
    s = strip(a, MINE, came_a, bag(a))
    wait(a, 10, lambda _: keys(a) == [])
    _, came_a = wear(a, SET['normal10'], s)
    a.logout()
    inventory_view('demo:item/krowaz_upper_normal10', 1, ITEM['demo:item/krowaz_upper_normal10']['label'])
    plain = normal(where, glow_off)
    # The set taken off both players: the default body draws in the parts' boxes.
    held['s'] = strip(b, SET['normal10'], held['came'], held['s'])
    wait(b, 10, lambda _: keys(b) == [])
    a = peer('explorer', create=False)
    strip(a, SET['normal10'], came_a, bag(a))
    wait(a, 10, lambda _: keys(a) == [])
    a.logout()
    work = root / 'build/pq319/moradon'
    with tempfile.TemporaryDirectory(dir=root / 'build') as config:
        bare_text = glow_client(work / 'armour-bare.ppm', config)
    assert not re.search(r'^EQUIPMENT_GLOW entity=\d+ self=\d key=(%s) ' % '|'.join(map(str, KEYS.values())),
                         bare_text, re.M), bare_text[-1500:]
    bare = captures(bare_text)
    names = [p[0] for p in PARTS]
    differs = {(w, n): changed_in(plain[0], bare[0], where[PEAK, w, n]) for w in ('self', 'other') for n in names}
    # A tenth of each part's box at least: the far player's helmet changed 368 of
    # its 2,368 pixels in a make live-ko run, the nearer parts a third or more.
    area = {(w, n): (where[PEAK, w, n][2] - where[PEAK, w, n][0] + 1) * (where[PEAK, w, n][3] - where[PEAK, w, n][1] + 1)
            for w in ('self', 'other') for n in names}
    assert all(v >= area[k] // 10 for k, v in differs.items()), (differs, area)
    print('PASS Moradon client draws the Krowaz Assassin artwork in place of the default body: pixels %d levels '
          'different in each part\'s box between the normal +10 set and the set taken off: %s; %s'
          % (LEVELS, {f'{w} {n}': v for (w, n), v in differs.items()}, to_png(bare[0])), flush=True)
drain(b)
b.logout()
