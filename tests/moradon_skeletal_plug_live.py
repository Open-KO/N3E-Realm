"""The 2233 client's skeletal weapon plug in Moradon (PQ-317): the
<selfname>'s Azagai bow on the local and another player, against the prepared
Moradon glow stack. A 2233/2145 addition (KO 1298 has none).

The package is the Moradon feature cook with --glow-2233
(packages/moradon-glow2233), which also carries the skeletal plugs of
games/moradon/skeletal-plugs-2233.json (tools/assetc/ko_chrplug_2145.py): the
2145 item 1110532000 (Item_Org column 40 = 1, so 2233 draws its
Item/11_1042_50_0.n3chrplug, by inference for 2145) as the package item
demo:item/azagai, worn only in the left hand, its appearance key with no rigid
mesh and an N3AT plug entry: the inner character chr\\11_1042_50_0.n3chr
(skeleton bow_boss_uer_h01, the enciphered clip table read by anim_2145) at the
plug matrix on the looks row's left-hand joint 7, playing breath (looped),
attackbreath and magic (once) as 0042df00 maps the player's clips (D-188: for
every wearer).

Two fresh accounts equip the bow over the wire (the server refuses it in the
right hand). With N3E_GRAPHICAL=1 the test client logs in as the first while
the second stands beside the spawn, and must draw the bow on both (ATTACHMENT,
no pulse); every sampled centre of the bow's drawn vertices must be the
wearer's frame x the joint matrix x the package's placement applied to the
skinned model's centre (from the drawn vertices); its breath must advance on
its own clock (four or more sample times, the skinned centre moving), and when
the other player casts Tiny Healing (the package's skill animation from KO
clip 17) the other's bow must play magic once, held at its end (KO frame 195,
the last key), then breath again. Captures at two breath phases: inside each
bow's screen box at least SWING of the pixels differ between them. Captures
and crops stay under build/pq317/moradon (KO artwork; never committed). No user
character is touched.

PQ-338: the 1298 client has no icon for this 2145-only item, so the package's
own icon map draws it with the 2145 icon the 2233 rule names (009b3fc0: the
Item_Ext_33 row 1000 has none, so Item_Org column 8, 111043200, printed
"%.2d" for an item / 10^9 of 1: UI/ItemIcon_11_1043_20_0.dxt), read from the
player's 2145 UI pack. Without a display the suite checks the cook's report
and that file's hash in the pack; with N3E_GRAPHICAL=1 the inventory window
(N3E_TEST_ITEM_TOOLTIP) shows the bow in the first account's left-hand slot
and, after it goes back to the bag, in its bag slot: each slot must draw an
icon whose pixels match that file's texels (and not their mirror image), and
its tooltip must name the 2145 item. Captures under build/pq338/moradon/bag.

PQ-337, PQ-350: the package also carries the bow on both of KO 2145's upgrade
paths (PQ-346), the same plug and model on their own keys: the normal +10
(1110432510: its own Item_Org row 1110432000, whose column 40 is also 1, and
Item_Ext_9 row 1510, attribute 4, so 2233's 0056ea30 gives it no glow) and the
reverse +1, +10 and +30 (1110532501, 1110532510, 1110532600: Item_Ext_33 rows
1501, 1510 and 1600, attribute 12, column 45 1, 10 and 30), whose glow 2233
hands to the plug's inner character (0056ea30 -> 0042de90 -> 00430f40): a
pulse at 1x, a steady light at 1x and a steady light at 2x. Each is named as
2233's tooltip (005aa8e0) names it: the Item_Ext name, and under it the kind
line, "(Unique Item)" or "(Reverse unique item)", both in the attribute's
colour (PQ-354: gold dcc77c for the normal +10, orange ffad4d for the reverse
grades, white for the plain bow), with "<selfname>" replaced by the viewer's
character name; the package's item-heads.bin (N3IH) must carry exactly those
heads and the token. The cook's report must show the four and their weapon
effect 32120 / 32121. With N3E_GRAPHICAL=1 the first account
wears the reverse +1 and the second the reverse +30; the client must draw each
glow on the whole bow (PLUG_GLOW at 1x and at 2x), its samples must follow the
pulse (+1) or stay at 1 (+30), and against a second client with
[Addition2233] EquipmentGlow=0 both bow boxes must be brighter at the pulse's
peak, and only the +30's at its trough. Then the first account wears the
normal +10: the client must draw no glow on it (no PLUG_GLOW for its key, its
box no brighter than with the option off) while the other's +30 still glows,
and must draw its weapon effect as the reverse grades' (APPEARANCE_EFFECT on
its key, in the PQ-342 run below). The inventory window names the reverse +1
and the normal +10 in the left-hand slot, each tooltip's head rows in their
colours in the capture (tests/tooltip_head.py). Captures under
build/pq337/moradon.

PQ-339: the grades' weapon effect is drawn as 2233 draws a CN3ChrTypePlug's,
rigid on the hand joint (CN3Chr::Render 00435440 -> 00433af0 -> RenderFX
004304c0 on the .n3chrplug's FX mesh): the cook's report must show 32120
(FX bundle version 6, read with ko_fx's 2233 layout) drawn on both grades'
keys from the player's 2145 fx pack (its 15 DXT5 frames), three copies of the
bow's 74-triangle FX mesh, and, since PQ-341, the tail 32121 (version 4) as
one 20 s clip of two 10 s links all four keys name. With N3E_GRAPHICAL=1 (and the
glow off in both, so only the effect differs) the client must draw it on both
players (APPEARANCE_EFFECT for the local +1 and the other's +30, three copies,
two tails, the poison trail colour), and against a client with
[WeaponEffect] EffectVisible=0 each bow box must hold, over both clock seconds,
EFFECT_PIXELS pixels GREEN levels greener with half that in red and at most
half in blue (the main bundle's green-yellow frames, added: blend 5/2), and at
each second TAIL_PIXELS pixels BLUE levels bluer with little green (PQ-341: the
tail's violet), each at least four times as many as the reverse comparison
finds. The glow captures above are taken with the effect off, so they compare
the glow alone. Captures under build/pq339/moradon.

PQ-342: the tail's four particle parts carry 2233's camera-distance rule
(00592900) as N3E4 rules (puffs: pool 20, 40 and 70 m; sparks: pool 11, 20
and 50 m). In the effect captures both tails lie within 20 m of the camera,
so the client's rule state (APPEARANCE_TAIL_THIN) must keep every pool there,
which those captures draw; then the other walks 25 m out from the spawn and
a client with the effect on must show, for its tail at 20-40 m, the puffs'
pool and the sparks' target trunc(11 x (50 - d) / 50) with at most one more
drawn per tail copy (a link counts the earlier link's taken live ones, as
2233's copy has one live list), every target matching 2233's formula for the
printed distance (at that range the sparks are a few pixels, so this side is
checked on the client's rule state, not by pixels).

PQ-347: the bow alone in the left hand selects the combat profile 1298 gives
a kind 70 bow (1298 client 0045bfe0: ready clip 92; its attack tick 004659b0 casts the
class's archery skill, row 108003 for the package's class 108: its clip 26,
due every 1.3 s + 0.15 s), as rows the glow cook adds for each grade. The
server's combat style (Entity field 22) must be the bow's on the wearer and
on the other player, and the unarmed style once the bow is back in the bag; a
third account wearing it at Moradon's first worm area must have its accepted
strikes 29 ticks apart (ceiling(1450 / 50)) with the tries between refused
as cooldown, each frozen with the bow's style (field 23). With
N3E_GRAPHICAL=1 the test client logs in as a fourth account wearing the bow
at the worms, presses Z then R (N3E_TEST_SHOWCASE_TARGET / _ATTACK): its own
drawn clip (WEARER_CLIP) must be the bow's ready 92 and then its shot 26, a
fifth account's strikes over the wire must draw 26 for it as an observer,
and neither may draw an unarmed clip (86, 87, 88, 15). PQ-416: the bow
profile is a ranged basic attack (ranged-attack.bin: reach 40 m, range 42 m
from the Azagai's range column 400, 1298 00583780 / 00468620, and 1298's text
4009; PQ-467: hold sqrt(40^2 + 1000) m on the ground plane, ranged-attack.bin
N3RH), so the third account first shoots a worm more than 8 m away (and
inside the ranged limit) from where it stands, without walking in. PQ-420:
the shot is held for 1298's cast (the archery row's 1.3 s, ranged-attack.bin
N3RC): the server's start event (kind 2, no hit) and its landing (kind 6) are
27 ticks apart (clip 26 stretched to 1.3 s reaches its marker at 0.2 + 1.3737
x 1.3 / 1.6 s), or a little more for the wear commit. PQ-421: each shot
needs and spends 1298's arrow (Item_Org 391010000, one per shot by the
archery row's type-2 count; 0057f7f0, 0046f3f1 / 004b0792): the hunter starts
with the package's 100 and has one fewer for every shot that landed
(PQ-444, D-224: for every shot released, also one whose worm died while
its arrow flew, as Ebenezer's flying phase spends it at the release). PQ-422
(D-219): the bow carries its 2145 Item_Org attack (116, column 16) under the
package's bow stats category, and each paced shot that lands deals 1298's
archery damage on an NPC (AI 0040d471 -> 00443a34's type-2 branch: the
operator's MAGIC_TYPE2 row 108003, HitRate 100, AddDamage 100,
AddDamagePlus 0) for the hunter's derived attack (World field 13) against
the package's NPC defence; a zero sum is a miss. PQ-434 (D-221, amending
D-219): each grade's attack and durability are 2145 Item_Org columns 16 and
20 plus its Item_Ext columns 9 and 13 (116 / 8000 for the plain bow; 182,
148, 163, 200 / 17000, 14000, 15000, 17000 for the grades) in the recipe and
in the hunter's granted bag; swapped in for the plain bow with no shot
between, the reverse +30 raises the hunter's derived attack, and its next two
landed shots fall within the archery bounds of that attack. PQ-423 (D-220): the cast
draws the archery row's self FX 500 (fx/arrow.fxb, the arrow) on joint 12 of
the archer, turned with its facing, from the shot's start until it lands, for
the archer's own client and for an observer of another archer (1298 00583f20
/ 00585a90 -> 00479de0; 00584b00 -> 0047a710). PQ-417 (D-222): the arrow
flies from the release. PQ-439 (D-223): the server releases each shot at its
landing tick (a kind-7 event, 27 ticks after the start) and lands it when its
arrow arrives, the 3-D distance at fx/arrow.fxb's 77 m/s later (a kind-6
event), as 1298's AI server applies the hit only on the effecting phase the
shooter's client sends at the arrow's collision (0047a8d0 -> Ebenezer
004630a6 -> AI 0040d471); the hunter tries again as soon as its shot is
released (1298's bow tick casts once an interval, 004659b0; neither it nor
005819e0 tests the flight: binary, by absence, PQ-439 evidence), so its tries
inside the interval are refused as cooldown while the arrow flies.

PQ-400: two clients with the same options (the effect and the glow off) must
capture the same bow boxes at each clock second (each wearer's layered base
clip now starts at first sight, not at the host's uptime, which put the bows a
pixel or more apart and lifted the reverse comparisons). A client that a
signal ends is reported with the signal and the host's memory then.
"""
import hashlib
import json
import math
import os
import pathlib
import re
import secrets
import signal
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
import ko_glow_2233  # noqa: E402
import pack_2145  # noqa: E402

root = pathlib.Path(__file__).resolve().parents[1]
os.chdir(root)
state = moradon_stack.state()
package = (moradon_stack.WORK / 'packages/moradon-glow2233').resolve()
assert state['release'] == (package / 'release.sha256').read_text().strip(), 'the stack must serve the glow package'
recipe = json.loads((package / 'recipe.json').read_text())['manifest']
assert recipe['engine_version'] == 39 and recipe['protocol_version'] == 30, (recipe['engine_version'],
                                                                             recipe['protocol_version'])
provenance = json.loads((moradon_stack.WORK / 'ko-moradon-glow2233/provenance.json').read_text())
plugs = provenance['skeletal_plugs_2233']
AZAGAI = b'demo:item/azagai'
# PQ-337, PQ-350: the plain bow, its normal +10 and three of its reverse
# grades, one plug file (one cooked model).
NORMAL, LOW, MIDDLE, TOP = ('demo:item/azagai_normal10', 'demo:item/azagai_reverse1', 'demo:item/azagai_reverse10',
                            'demo:item/azagai_reverse30')
GRADES = {'demo:item/azagai': 1110532000, NORMAL: 1110432510, LOW: 1110532501, MIDDLE: 1110532510, TOP: 1110532600}
UPGRADES = [i for i in GRADES if i != 'demo:item/azagai']
entry = plugs['entries'][0]
assert [e['ko_2145_item'] for e in plugs['entries']] == list(GRADES.values()), plugs['entries']
assert all(e['plug_sha256'] == entry['plug_sha256'] and e['slots'] == entry['slots'] for e in plugs['entries'])
assert entry['plug'] == 'Item\\11_1042_50_0.n3chrplug' and entry['plug_sha256'] == \
    '37a34d10bbfe16df620b749fad44a61e508a2ab81d0563eb6afbfd83714db09b', entry['plug']
assert [(s['slot'], s['name']) for s in entry['slots']] == [(0, 'breath'), (1, 'attackbreath'), (2, 'magic'),
                                                           (3, 'breath')], entry['slots']
# 005aa8e0: the Item_Ext name for attributes 4 and 12 (the label), and the
# head (PQ-354, D-194): the name's colour by attribute (005aac3c: 0 white, 4
# gold +0x12c, 12 orange +0x158, 005a9160's constants) and the kind line in
# the same colour (texts 6811 and 6816 of the player's 2145 Texts_us.tbl).
LABELS = ["<selfname>'s Azagai", "<selfname>'s Azagai(+10)", "<selfname>'s Azagai(+1)", "<selfname>'s Azagai(+10)",
          "<selfname>'s Azagai(+30)"]
UNIQUE, REVERSE = ('(Unique Item)', 0xdcc77c), ('(Reverse unique item)', 0xffad4d)
HEADS = [(0xffffff, []), (0xdcc77c, [UNIQUE]), (0xffad4d, [REVERSE]), (0xffad4d, [REVERSE]), (0xffad4d, [REVERSE])]
assert [plugs['items'][i]['name'] for i in GRADES] == LABELS, plugs['items']
assert [(plugs['items'][i]['head']['name_color'], [(x['text'], x['color']) for x in plugs['items'][i]['head']['lines']])
        for i in GRADES] == HEADS, plugs['items']
import item_heads  # noqa: E402
token, cooked_heads = item_heads.parse((package / 'item-heads.bin').read_bytes(), recipe['game_id'],
                                       {i['id'] for i in recipe['inventory']['items']})
assert token == '<selfname>' and [cooked_heads[i] for i in GRADES] == HEADS, (token, cooked_heads)
# The normal +10 is its own Item_Org row (1110432000, column 40 = 1: the same
# .n3chrplug) on Item_Ext_9; the reverse grades are 1110532000's on Item_Ext_33.
assert [(plugs['items'][i]['id'], plugs['items'][i]['skeletal'], plugs['items'][i]['extension_table'],
         plugs['items'][i]['extension_key'], plugs['items'][i]['attribute'], plugs['items'][i]['column_45'],
         plugs['items'][i]['kind_text']) for i in GRADES] == [
    (1110532000, 1, 33, 1000, 0, 0, None), (1110432000, 1, 9, 1510, 4, 0, 6811), (1110532000, 1, 33, 1501, 12, 1, 6816),
    (1110532000, 1, 33, 1510, 12, 10, 6816), (1110532000, 1, 33, 1600, 12, 30, 6816)], plugs['items']
KEY = 1 + [r['item'] for r in recipe['appearance']].index('demo:item/azagai')
KEYS = {i: 1 + [r['item'] for r in recipe['appearance']].index(i) for i in GRADES}
MAGIC = next(s for s in entry['slots'] if s['name'] == 'magic')
assert (MAGIC['start'], MAGIC['end'], MAGIC['fps']) == (160.0, 195.0, 55.0), MAGIC

# The N3AT plug entry as the client reads it (tools/assetc/attachments.py):
# header 40 bytes, then key .. lit, four clip records, the placement, the map.
table = (package / 'attachments.bin').read_bytes()
assert table[:4] == b'N3AT' and struct.unpack_from('<I', table, 36)[0] == len(GRADES), table[:40]
at, placements, maps = 40, [], []
for item in GRADES:
    base = struct.unpack_from('<IIfIIfI', table, at)
    assert base == (KEYS[item], 7, 1.0, 0, 4, 1.0, 0), (item, base)
    placements.append(list(struct.unpack_from('<12f', table, at + 28 + 80)))
    rows = struct.unpack_from('<I', table, at + 28 + 80 + 48)[0]
    maps.append([struct.unpack_from('<4I', table, at + 28 + 80 + 52 + 16 * i) for i in range(rows)])
    at += 28 + 80 + 52 + 16 * rows
assert len(table) == at and all(p == placements[0] for p in placements) and all(m == maps[0] for m in maps), len(table)
PLACEMENT, MAP = placements[0], maps[0]
assert (2, 0, 2, 1) in MAP and (0, 0, 0, 0) in MAP, MAP  # Tiny Healing -> magic once; idle -> breath

# PQ-338: the bow's icon, by the 2233 rule from the player's 2145 UI pack.
ICON = 'UI/ItemIcon_11_1043_20_0.dxt'
icon_row = {x['item']: x for x in provenance['hud']['item_icons']}['demo:item/azagai']
assert (icon_row['path'], icon_row['base'], icon_row['extension'], icon_row['item_2233'], icon_row['rule'],
        icon_row['assets']) == (ICON, 111043200, 0, 1110532000, '009b3fc0', '2145'), icon_row
shown_icon = provenance['glow_2233']['presentation']['skeletal_icons']['items']
assert [(x['item'], x['item_org_icon'], x['item_ext'], x['item_ext_icon'], x['path']) for x in shown_icon] == [
    ('demo:item/azagai', 111043200, 1000, 0, ICON), (NORMAL, 111043200, 1510, 0, ICON), (LOW, 111043200, 1501, 0, ICON),
    (MIDDLE, 111043200, 1510, 0, ICON), (TOP, 111043200, 1600, 0, ICON)], shown_icon
ui_pack = pack_2145.Pack(ko_glow_2233.INSTALL / 'client/UI/ui.hdr')
ICON_DATA = ui_pack.read(ICON.split('/', 1)[1])
assert hashlib.sha256(ICON_DATA).hexdigest() == icon_row['sha256'], icon_row


def x8r8g8b8(data):
    """(width, height, RGBA) of an unmipmapped NTF3 X8R8G8B8 texture, read here
    rather than with the cook's decoder: a name, NTF\\x03, width, height,
    format 22, no mipmaps, then B, G, R, X bytes per texel (0043f090)."""
    n = struct.unpack_from('<i', data, 0)[0]
    assert data[4 + n:8 + n] == b'NTF\x03', data[:16]
    w, h, fmt, mips = struct.unpack_from('<4i', data, 8 + n)
    raw = data[24 + n:]
    assert (fmt, mips, len(raw)) == (22, 0, w * h * 4), (fmt, mips, len(raw))
    return w, h, b''.join(bytes((raw[i + 2], raw[i + 1], raw[i], 255)) for i in range(0, len(raw), 4))


# PQ-337, PQ-350: the reverse grades' glow (2233 0056ea30 on Item_Ext_33 rows
# 1501, 1510 and 1600: attribute 12, column 45 1, 10 and 30) handed to the
# plug's inner character (0042de90, 00430f40), none for the normal +10
# (attribute 4); PQ-339: the four grades' weapon effect's main bundle drawn on
# the FX mesh; PQ-341: and its tail, one clip the four keys share.
glows = {g['item']: g for g in provenance['glow_2233']['glow']}
assert [(g['key'], g['glow_2145_item'], g['extension_key'], g['attribute'], g['column_45'], g['wave'], g['modulate'],
         g['skeletal_plug']) for i, g in glows.items() if i in GRADES] == [
    (KEYS[LOW], 1110532501, 1501, 12, 1, 'pulse', 1, 'Item/11_1042_50_0.n3chrplug'),
    (KEYS[MIDDLE], 1110532510, 1510, 12, 10, 'steady', 1, 'Item/11_1042_50_0.n3chrplug'),
    (KEYS[TOP], 1110532600, 1600, 12, 30, 'steady', 2, 'Item/11_1042_50_0.n3chrplug')], glows
assert NORMAL not in glows and plugs['items'][NORMAL]['glow'] is None, glows
assert len(provenance['glow_2233']['glow']) == 15, provenance['glow_2233']['glow']
effects = {i: plugs['items'][i]['effect'] for i in GRADES}
TAIL_PARTS = [[0, 3, 8, 3], [1, 3, 8, 3], [2, 1, 9, 3], [3, 1, 9, 3], [4, 1, 9, 3], [5, 1, 9, 3]]
assert effects['demo:item/azagai'] is None and all(
    (e['main_id'], e['main']['file'], e['main']['version'], e['main']['parts'], e['tail']['file'],
     e['tail']['version'], e['tail']['parts'], e['tail']['unread'], e['trace_color'], e['drawn']) == (
        32120, 'fx\\poison_wepon_2011_all.fxb', 6, [[0, 2, 8, 4]], 'fx\\corea_new_tail_poision_bow.fxb', 4,
        TAIL_PARTS, 2, 'ffff00ff', dict(main=True, tail=True)) and e['reason'] is None
    for i, e in effects.items() if i != 'demo:item/azagai'), effects
drawn = {a['key']: a for a in provenance['effects']['appearance'] if a.get('layout') == '2233'}
assert sorted(drawn) == sorted(KEYS[i] for i in GRADES if i != 'demo:item/azagai') and all(
    (a['item'], a['main'], a['main_id'], a['tail'], a['frames'], a['copies'], a['triangles'], a['tails'],
     a['trace_color']) == (GRADES[i], 'fx\\poison_wepon_2011_all.fxb', 32120, 'fx\\corea_new_tail_poision_bow.fxb',
                           15, 3, 222, 2, 'ffff00ff')
    for i in GRADES if i != 'demo:item/azagai' for a in [drawn[KEYS[i]]]), drawn
# PQ-341: the tail as a 20 s clip of two 10 s links (its two meshes cycle 50
# frames at 15 and 40 a second), both keys naming the first key's clip.
TAIL_CLIP = 'appearance-%d-tail' % KEYS[NORMAL]
assert all((a['tail_2233']['link_seconds'], a['tail_2233']['frames'], a['tail_2233']['parts'], a['tail_2233']['scale'],
            a['tail_2233']['clip']) == (10.0, 600, [[3, 8], [3, 8], [1, 9], [1, 9], [1, 9], [1, 9]], True, TAIL_CLIP)
           for a in drawn.values()), drawn
fx_sources = provenance['skeletal_effects_2233']['sources']
assert sum(1 for n in fx_sources if n.startswith('fx/billboard\\japan_2010_a_sild_alll\\poison_2011_wefx_')) == 15 \
    and {'fx/fx.hdr', 'fx/fx.src', 'fx/poison_wepon_2011_all.fxb', 'fx/corea_new_tail_poision_bow.fxb'} <= set(
        fx_sources) and sum(1 for n in fx_sources if n.startswith('fx/object\\20070322_mine_hand_fx0')) == 6 \
    and sum(1 for n in fx_sources if n.startswith('fx/particle\\quest_re_plus\\')) == 4, fx_sources
assert [(e['key'], e['fx_vertices'], e['fx_triangles'], e['tail_drawn']) for e in
        provenance['skeletal_effects_2233']['effects']] == [(KEYS[i], 74, 74, True) for i in UPGRADES]
# PQ-342: each particle part's camera-distance rule (2233 00592900) on the
# shared clip: pool 20, 40 and 70 m for the kind-2 puffs (parts 2 and 3), pool
# 11, 20 and 50 m for the kind-1 sparks (parts 4 and 5), written as N3E4.
RULES = [(20, 40.0, 70.0), (20, 40.0, 70.0), (11, 20.0, 50.0), (11, 20.0, 50.0)]
assert all([(r['count'], r['near'], r['far']) for r in a['tail_2233']['thinning']] == RULES
           for a in drawn.values()), drawn
# N3E4 rules; since PQ-376 the file is N3E5 (the 1298 blade's sort records)
# and the 2233 effects carry no sort record.
assert (package / 'effects.bin').read_bytes()[:4] == b'N3E5', 'cook the glow package with PQ-376'
assert all('sort' not in a for a in drawn.values()), drawn
print(f"PASS PQ-342: the Azagai tail's four particle parts carry 00592900's camera-distance rules {RULES} (pool, "
      f"near, far) as N3E4 rules on its clip (N3E5 since PQ-376; no sort record on the 2233 effects)", flush=True)
print("PASS the glow package carries the <selfname>'s Azagai on both upgrade paths: the normal +10 (1110432510: "
      "Item_Org 1110432000, column 40 = 1, Item_Ext_9 row 1510, attribute 4) without a glow record, and the reverse "
      "+1, +10 and +30 (1110532501, 1110532510, 1110532600: Item_Ext_33 rows 1501, 1510 and 1600, attribute 12, "
      "column 45 1, 10 and 30), whose keys glow (a pulse at 1x, a steady light at 1x and at 2x, handed to the plug by "
      "0042de90 / 00430f40); labels %s (005aa8e0's name) with their N3IH heads %s (PQ-354: the name's colour and "
      "the kind line, the token <selfname>); all four grades' weapon effect 32120 / 32121 "
      "resolves (0056bb50, else Item_Ext column 5) to bundle versions 6 and 4, both read with ko_fx's 2233 layout; "
      "PQ-339: 32120 (a billboard part, version 8, base 4) is drawn on each grade's key, three copies of the bow's "
      "74-triangle FX mesh with its 15 DXT5 frames from the 2145 fx pack; PQ-341: and 32121 (two mesh and four "
      "particle parts) as a 20 s tail clip of two 10 s links the four keys share; the plain row 1000 has neither"
      % (LABELS, [(f'{c:06x}', [x for x, _ in lines]) for c, lines in HEADS]), flush=True)

ICON_TEXELS = x8r8g8b8(ICON_DATA)
assert ICON_TEXELS[:2] == (64, 64), ICON_TEXELS[:2]
assert AZAGAI in (package / 'hud.bin').read_bytes(), 'hud.bin has no icon record for the Azagai'
print(f"PASS the glow package's own icon map draws the <selfname>'s Azagai with {ICON} (2233 009b3fc0: Item_Org "
      f"icon 111043200, Item_Ext_33 row 1000 none, \"%.2d\" for item / 10^9 = 1) from the player's 2145 UI pack "
      f"({icon_row['sha256'][:12]}, 64 x 64)", flush=True)

env = {**os.environ, 'N3E_IMAGE': moradon_stack.IMAGE, 'N3E_PACKAGE_PATH': str(package), 'N3E_PORT': str(state['port']),
       'N3E_REALM': state['realm']}
RIGHT, LEFT = 0, 1
# The local player's drawn seconds: two breath phases half a cycle (0.878 s) apart.
A, B = 6.0, 6.88
SWING = 0.05  # share of a bow box's pixels that differ between the captures
OUT = root / 'build/pq317/moradon'
accounts = {}
for role in ('archer', 'companion'):
    account = 'plug' + role[:4] + secrets.token_hex(5)
    password = secrets.token_urlsafe(24)
    subprocess.run(['docker', 'compose', '-p', moradon_stack.PROJECT, 'exec', '-T', 'server', 'n3e-server',
                    'account-create', account], input=password + '\n', text=True, env=env, capture_output=True,
                   check=True)
    accounts[role] = (account, password)
serial = [0]


names = {}  # role: its character's name (the tooltip's <selfname>, PQ-354)


def peer(role, create=True):
    account, password = accounts[role]
    p = Peer(state['port'], account, password, content=state['release'], game=recipe['game_id'],
             protocol=recipe['protocol_version'])
    p.select(p.create(role.title() + secrets.token_hex(3)) if create else p.characters[0][0])
    names[role] = p.characters[0][1]
    return p


def host_memory():
    """PQ-400: the host's memory state, for a client a signal ended: MemAvailable
    and SwapFree (kB), the memory pressure line, and the OOM kills counted in this
    process's cgroup and each parent (memory.events oom_kill). The kernel and
    systemd-oomd log their kills; a SIGKILL from another process leaves nothing
    else to read."""
    out = {}
    try:
        info = dict(line.split(':', 1) for line in pathlib.Path('/proc/meminfo').read_text().splitlines())
        out.update({k: info[k].strip() for k in ('MemAvailable', 'SwapFree') if k in info})
        out['pressure'] = pathlib.Path('/proc/pressure/memory').read_text().splitlines()[-1]
        group = pathlib.Path('/sys/fs/cgroup') / pathlib.Path('/proc/self/cgroup').read_text().split('::', 1)[1].strip().lstrip('/')
        kills = {}
        while group != pathlib.Path('/sys/fs/cgroup').parent and (group / 'memory.events').is_file():
            events = dict(line.split() for line in (group / 'memory.events').read_text().splitlines())
            kills[group.name] = int(events.get('oom_kill', 0))
            group = group.parent
        out['oom_kill'] = kills
    except (OSError, ValueError, IndexError, KeyError) as error:
        out['unreadable'] = repr(error)
    return out


def exited(code, text, tail=1500):
    """A test client's exit: 0, or the code, the signal that ended it (with the
    host's memory then, PQ-400) and the end of its log. A signal the enum does
    not name (a real-time one) is given by its number (PQ-410)."""
    if code == 0:
        return
    ended = {}
    if code < 0:
        try:
            name = signal.Signals(-code).name
        except ValueError:
            name = str(-code)
        ended = {'signal': name, 'memory': host_memory()}
    raise AssertionError((code, ended, text[-tail:]))


def wait(p, tag, predicate=lambda d: True, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        t, d = p.receive()
        assert t != 4, (t, d)
        if t == tag and predicate(d):
            return d
    raise AssertionError(('timeout', tag))


def bag(p, op=0, source=0, destination=0, s=None, status=b'committed'):
    time.sleep(.22)  # inside the shared inventory request budget
    if not op:
        p.send(32, b'')
        return fields(first(wait(p, 33, lambda d: first(d, 2) == b'ok'), 3))
    serial[0] += 1
    records = s[6] if op == 6 else s[5]
    p.send(32, integer(1, op) + blob(2, f'pq317-{secrets.token_hex(4)}-{serial[0]}') + integer(3, first(s, 1))
           + integer(4, source) + integer(5, destination) + integer(6, first(fields(records[source]), 1)))
    d = wait(p, 33)
    assert first(d, 2) == status, (status, d)
    return fields(first(d, 3))


def keys(p):
    return list(first(p.entities.get(p.id, {}), 20, b''))


def track_attack(p):
    """PQ-422: record the player's derived attack (owner-only World field 13,
    DerivedStats attack 1) from every World message `p` parses, in
    `p.attacks`, without waiting for one (the paced loop's timing stays)."""
    p.attacks = []
    parse = p._parse

    def tracked(envelope):
        tag, data = parse(envelope)
        if tag == 10 and 13 in data:
            p.attacks.append(first(fields(first(data, 13)), 1))
        return tag, data
    p._parse = tracked


def strike(p, target, released=False):
    """An attack request and its result: (status, damage) (Peer.action's
    request, keeping ActionResult field 4), matched by sequence; results of
    earlier shots that arrive meanwhile are kept for `result_of`. PQ-439
    (D-223): with `released`, an accepted shot returns ('released', 0) as
    soon as the requester's strike fields show it released; its result comes
    when its arrow arrives (`result_of`). PQ-444: every sequence the
    requester's strike fields show released is kept (`released`), so a shot
    whose result came first still counts as released."""
    results = p.__dict__.setdefault('results', {})
    casts = p.__dict__.setdefault('casts', {})
    shown = p.__dict__.setdefault('released', set())
    p.action_seq += 1
    seq = p.action_seq
    p.send(15, integer(1, p.session) + integer(2, seq) + integer(3, target) + blob(4, p.action_id))
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        tag, data = p.receive()
        if tag == 16:
            results[first(data, 1)] = (first(data, 2, b'').decode(), first(data, 4))
        me = p.entities.get(p.id)
        if tag == 10 and me and first(me, 14) == b'released':
            shown.add(first(me, 30))
        if tag == 10 and me and first(me, 30) == seq and first(me, 10):
            casts.setdefault(seq, (first(me, 10), first(me, 23)))  # accepted: (strike tick, style)
        if seq in results:
            return results.pop(seq)
        if released and tag == 10 and me and first(me, 30) == seq and first(me, 14) == b'released':
            return 'released', 0
    raise AssertionError(('no result', seq))


def result_of(p, seq, seconds=6):
    """PQ-439: the (status, damage) of an earlier released shot `seq`."""
    results = p.__dict__.setdefault('results', {})
    shown = p.__dict__.setdefault('released', set())
    deadline = time.monotonic() + seconds
    while seq not in results:
        assert time.monotonic() < deadline, ('no result', seq)
        tag, data = p.receive()
        if tag == 16:
            results[first(data, 1)] = (first(data, 2, b'').decode(), first(data, 4))
        me = p.entities.get(p.id)
        if tag == 10 and me and first(me, 14) == b'released':
            shown.add(first(me, 30))
    return results.pop(seq)


def flight_ticks(event, speed=77.0):
    """PQ-439 (D-223): the server's flight of a release event (kind 7): the
    3-D distance between its positions (fields 11-13 and 14-16) in f32, over
    the flight's speed, x 20, rounded up (ranged_shot.rs flight_ticks)."""
    def f32(value):
        return struct.unpack('<f', struct.pack('<f', value))[0]
    a = [f32(first(event, k, 0.0)) for k in (11, 12, 13)]
    b = [f32(first(event, k, 0.0)) for k in (14, 15, 16)]
    square = 0.0
    for k in range(3):
        d = f32(b[k] - a[k])
        square = f32(square + f32(d * d))
    return min(200, math.ceil(f32(math.sqrt(square)) / f32(speed) * 20))


def archery_damage(attack, defense, hit):
    """PQ-422 (D-219): (lowest, highest) damage of a type-2 HitType 0 hit
    (AI 00443a34's skill branch, its f32 constants as exact rationals) plus
    AddDamagePlus: base trunc(AddDamage x 0.01f x (attack x 200 / (defence +
    240))), damage trunc(base x 0.6f + r x 0.89f + 0.99) for r in 0..=base."""
    from fractions import Fraction

    def f32(value):
        return Fraction(struct.unpack('<f', struct.pack('<f', value))[0])
    c099 = Fraction(struct.unpack('<d', struct.pack('<II', 0x7AE147AE, 0x3FEFAE14))[0])
    base = math.floor(hit['add_damage'] * f32(.01) * (attack * 200 // (defense + 240)))
    return (hit['add_damage_plus'] + math.floor(f32(.6) * base + c099),
            hit['add_damage_plus'] + math.floor(f32(.6) * base + f32(.89) * base + c099))


def arrows(p):
    """PQ-421: the arrows in the first bag slot holding them (0: none)."""
    found = [first(fields(r), 3) for r in bag(p)[5] if first(fields(r), 2) == ARROW.encode()]
    return found[0] if found else 0


def equip(p):
    """The bow from the bag: refused in the right hand, worn in the left;
    (state, the bag slot it came from)."""
    s = bag(p)
    at = next(i for i, r in enumerate(s[5]) if first(fields(r), 2) == AZAGAI)
    bag(p, 5, at, RIGHT, s, status=b'incompatible_slot')
    s = bag(p, 5, at, LEFT, s)
    wait(p, 10, lambda _: keys(p) == [KEY])
    return s, at


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


def frame(sample):
    """The drawn centre the package's rule gives for a PLUG_SAMPLE: the
    wearer's position and heading x the joint matrix x the placement, applied
    to the centre of the skinned model."""
    m = sample['model']
    local = [sum(PLACEMENT[r * 4 + c] * m[c] for c in range(3)) + PLACEMENT[r * 4 + 3] for r in range(3)]
    j = sample['joint_matrix']
    v = [sum(j[c * 3 + r] * local[c] for c in range(3)) + j[9 + r] for r in range(3)]
    c, s = math.cos(sample['heading']), math.sin(sample['heading'])
    w = sample['wearer']
    return [w[0] + v[0] * c + v[2] * s, w[1] + v[1], w[2] - v[0] * s + v[2] * c]


def plug_samples(text):
    out = []
    for m in re.finditer(r'^PLUG_SAMPLE entity=(\d+) entry=0 slot=(\d) time=(\S+) model=(\S+) bounds=(\S+) placed=(\S+) '
                         r'heading=(\S+) joint_matrix=(\S+) wearer=(\S+)$', text, re.M):
        vec = lambda g: [float(v) for v in g.split(',')]  # noqa: E731
        out.append(dict(entity=int(m[1]), slot=int(m[2]), time=float(m[3]), model=vec(m[4]), bounds=vec(m[5]),
                        placed=vec(m[6]), heading=float(m[7]), joint_matrix=vec(m[8]), wearer=vec(m[9])))
    return out


def share(a, b, box, levels=24):
    """The fraction of `box`'s pixels whose channel sum differs by at least
    3 x `levels` between captures `a` and `b`."""
    width, height, pa = npc_looks_live.read_ppm(a)
    _, _, pb = npc_looks_live.read_ppm(b)
    x0, y0, x1, y1 = box
    hits = total = 0
    for y in range(max(0, y0), min(height, y1 + 1)):
        for x in range(max(0, x0), min(width, x1 + 1)):
            i = (y * width + x) * 3
            total += 1
            hits += abs(sum(pa[i:i + 3]) - sum(pb[i:i + 3])) >= 3 * levels
    return hits / max(1, total)


def png(path, width, height, rows):
    raw = b''.join(b'\0' + bytes(r) for r in rows)
    chunk = lambda kind, data: (struct.pack('>I', len(data)) + kind + data  # noqa: E731
                                + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


sx, sz = recipe['gameplay']['spawn_x'], recipe['gameplay']['spawn_z']
a = peer('archer')
_, archer_at = equip(a)
a.logout()
b = peer('companion')
_, companion_at = equip(b)
# Ahead of the camera's opening view (towards -z), else the first open side.
for dx, dz in ((0, -2.5), (2.5, 0), (-2.5, 0), (0, 2.5)):
    if walk(b, sx + dx, sz + dz):
        break
print(f"PASS two Moradon accounts equip the <selfname>'s Azagai (2145 item 1110532000) in the left hand over the "
      f"wire (the server refuses it in the right hand) and carry appearance key {KEY}", flush=True)

# PQ-347: the bow alone in the left hand selects the combat profile 1298 gives
# a kind 70 bow (1298 client 0045bfe0: ready 92; 004659b0: the class's archery cast, whose
# row 108003 plays clip 26 and is due every 1.3 s x 1 + 0.15 s), as package
# rows the server's combat style reads from committed equipment.
bow = provenance['bow_combat_1298']
assert (bow['skill'], bow['animation'], bow['cast_tenths']) == (108003, 26, 13), bow
assert [r['item'] for r in bow['rows']] == list(GRADES) and all(r['kind'] == 70 for r in bow['rows']), bow
combat = recipe['combat_animation']
BOW = bow['rows'][0]['profile']
profile = combat['profiles'][BOW - 1]
clip = lambda i: combat['clips'][i]['source']  # noqa: E731
assert (clip(profile['ready']), [clip(i) for i in profile['attacks']], clip(profile['moving']),
        profile['interval_ms']) == ('player-combat-92.bin', ['player-combat-26.bin'], 'player-combat-26.bin', 1450), \
    profile
assert sorted(tuple(r['items']) for r in combat['rows'] if r['profile'] == BOW) == sorted(
    (None, i) for i in GRADES), combat['rows']
UNARMED = next(r['profile'] for r in combat['rows'] if r['items'] == [None, None])
# PQ-416 (D-216): that profile is 1298's archery as a ranged basic attack.
# PQ-421 (D-218): one arrow (1298 Item_Org 391010000) per shot, text 4007.
# PQ-422 (D-219): the archery row 108003's MAGIC_TYPE2 terms.
# PQ-423 (D-220): its self FX 500 on part 12 as the cast effect.
ARROW = 'demo:item/arrow'
# PQ-417 (D-222): its flying FX 590 from part 12 at fx/arrow.fxb's 77 m/s,
# its target FX 550 at the target's part 0, the bow's release sound 0x157c.
FLIGHT = dict(clip='ranged-flight-590', joint=12, speed=77.0, hit_clip='ranged-hit-550', hit_joint=0,
              release='ranged-release')
assert (provenance['archery_flight_1298']['release_sound'], provenance['archery_flight_1298']['hit_life']) == (5500, .5), \
    provenance['archery_flight_1298']
assert recipe['ranged_attack'] == dict(profiles=[dict(profile=BOW, reach=40.0, range=42.0, cast_ms=1300,
                                                      ammo=dict(item=ARROW, count=1),
                                                      skill_hit=dict(hit_rate=100, add_damage=100,
                                                                     add_damage_plus=0),
                                                      cast_effect=dict(clip='ranged-cast-500', joints=[12]),
                                                      flight=FLIGHT,
                                                      # PQ-467 (D-233): Ebenezer's Type1 2 bound (004c1dbe)
                                                      # for the Azagai's 400 on the ground plane.
                                                      hold=dict(distance=math.sqrt(40 ** 2 + 1000), plane='xz'))],
                                       notice='Skill Failed - Too far',
                                       ammo_notice='Skill Failed - Not enough item'), recipe['ranged_attack']
ARROWS = next(i for i in recipe['inventory']['items'] if i['id'] == ARROW)
assert ARROWS == dict(id=ARROW, label='Arrow', stack_limit=9999, durability=0, starting=100), ARROWS
assert (provenance['arrows_1298']['exhaust_item'], provenance['arrows_1298']['arrows_per_shot']) == (391010000, 1)
# PQ-434 (D-221, amending D-219): each grade's attack is 2145 Item_Org column
# 16 + its Item_Ext column 9 and its durability column 20 + Item_Ext column
# 13 (2233 005aa8e0's attack and maximum durability lines; 1298's per-number
# ITEM rows, Ebenezer 0041f077), all under the bow category.
GRADE_STATS = {'demo:item/azagai': (116, 0, 8000, 0), NORMAL: (116, 66, 8000, 9000), LOW: (116, 32, 8000, 6000),
               MIDDLE: (116, 47, 8000, 7000), TOP: (116, 84, 8000, 9000)}
assert {i['id']: (i['category'], i['attack']) for i in recipe['stats']['items'] if i['id'] in GRADES} == {
    i: ('demo:weapon/bow', a + b) for i, (a, b, _, _) in GRADE_STATS.items()}, recipe['stats']['items']
assert {i['id']: i['durability'] for i in recipe['inventory']['items'] if i['id'] in GRADES} == {
    i: d + e for i, (_, _, d, e) in GRADE_STATS.items()}, recipe['inventory']['items']
assert {r['item']: (r['item_org_damage'], r['item_ext_damage'], r['item_org_durability'], r['item_ext_durability'])
        for r in provenance['bow_stats_2145']['items']} == GRADE_STATS, provenance['bow_stats_2145']
print(f"PASS the Azagai grades carry their upgrade stats (PQ-434, D-221): attack and durability "
      f"{[(a + b, d + e) for a, b, d, e in GRADE_STATS.values()]} (2145 Item_Org columns 16 and 20 + Item_Ext "
      f"columns 9 and 13) under the bow category", flush=True)
# PQ-420 (D-217): clip 26 stretched to the archery row's 1.3 s reaches its
# first marker after blend + marker x 1.3 / duration seconds.
shot_clip = combat['clips'][combat['profiles'][BOW - 1]['attacks'][0]]
LAND = math.ceil((struct.unpack('<f', struct.pack('<f', shot_clip['blend']))[0]
                  + struct.unpack('<f', struct.pack('<f', shot_clip['markers'][0]))[0] * 1.3
                  / struct.unpack('<f', struct.pack('<f', shot_clip['duration']))[0]) * 20)
assert LAND == 27, (LAND, shot_clip)
assert provenance['ranged_attack_1298']['item_range'] == 400, provenance['ranged_attack_1298']
LIMIT = recipe['melee']['actor_radius'] + recipe['melee']['target_radius'] + 42.0
MELEE = (recipe['melee']['actor_radius'] + recipe['melee']['target_radius']) * .5 + recipe['melee']['reach']
assert clip(combat['profiles'][UNARMED - 1]['ready']) == 'player-combat-86.bin'


def style(p, who=None):
    return first(p.entities.get(p.id if who is None else who, {}), 22)


a = peer('archer', create=False)
wait(a, 10, lambda _: b.id in a.entities)
b.pump(.5)
assert style(a) == BOW and style(b) == BOW and style(a, b.id) == BOW and style(b, a.id) == BOW, (
    style(a), style(b), style(a, b.id), style(b, a.id))
s = bag(a)
s = bag(a, 6, LEFT, archer_at, s)
wait(a, 10, lambda _: style(a) == UNARMED)
wait(b, 10, lambda _: style(b, a.id) == UNARMED)
s = bag(a, 5, archer_at, LEFT, s)
wait(a, 10, lambda _: style(a) == BOW)
wait(b, 10, lambda _: style(b, a.id) == BOW)
a.logout()
print(f"PASS the Azagai alone in the left hand is combat style {BOW} (1298's bow: ready clip 92, the archery row "
      f"108003's clip 26, 1450 ms) on the wearer and on the other player, and back to the unarmed style {UNARMED} "
      f"when it goes back to the bag", flush=True)


def run(p, x, z, tolerance=.5, seconds=40):
    start = time.monotonic()
    end, trail = start + seconds, []
    while time.monotonic() < end:
        p.pump(.05)
        me = p.entities[p.id]
        dx, dz = x - first(me, 3), z - first(me, 5)
        d = math.hypot(dx, dz)
        if d < tolerance:
            p.move(0, 0)
            p.pump(.2)
            return
        # PQ-437: where the walk was each second, for a blocked route's error.
        if not trail or time.monotonic() - start >= len(trail):
            trail.append((round(time.monotonic() - start, 1), round(first(me, 3), 2), round(first(me, 5), 2)))
        p.move(dx / max(1, d), dz / max(1, d), mode=1)
    me = p.entities[p.id]
    raise AssertionError(('route blocked', x, z, dict(
        at=(round(first(me, 3), 2), round(first(me, 5), 2)), trail=trail[:3] + trail[-6:],
        notices=list(p.notices.items()))))


# PQ-437: the hunter shoots only the worms of the area its route ends at
# (Moradon's worm area 0). With those five dead (each hit kills: 7 HP; a miss
# leaves the worm alive; 30 s respawn), the nearest live worm is a fresh spawn
# in area 1, more than the ranged limit away, and the straight walk there from
# area 0 stops on an object near (7, -30), the one the demo route to area 1
# turns around at (4, -28). So the hunt waits for area 0's respawn instead. A
# worm counts for the spawn area its position is nearest.
AREAS = [w['area'] for w in provenance['features']['worm']]
assert provenance['features']['worm'][0]['route'][-1] == provenance['features']['worm'][0]['point'], \
    provenance['features']['worm']


def area_of(e):
    x, z = first(e, 3), first(e, 5)
    return min(range(len(AREAS)), key=lambda i: math.hypot(max(AREAS[i][0] - x, 0, x - AREAS[i][2]),
                                                            max(AREAS[i][1] - z, 0, z - AREAS[i][3])))


def prey(p):
    """The live worms of area 0 that `p` sees."""
    return [e for e in p.entities.values() if first(e, 9) and first(e, 7) and area_of(e) == 0]


# The server freezes the bow's interval and style with each accepted strike:
# a third account wears the bow at Moradon's first worm area and strikes a
# worm again as soon as each reply arrives (PQ-439: or its shot is released);
# the strikes it accepts are at least 29 ticks apart (1450 ms at 50 ms:
# ceiling(1450 / 50)), the closest pair at most a tick over (a try lands that
# late; since PQ-439 the hunter takes another worm in reach while its arrow
# flies, since a kill now lands after the interval and a same-worm retry
# would wait for the death to show, PQ-448), the tries between are refused as
# cooldown, and every
# accepted strike carries the bow's style (field 23). PQ-444 (D-224): each
# shot's arrow goes in a durable write at its release (27 ticks), and the
# result comes when the arrow arrives.
hunter = 'plughunt' + secrets.token_hex(5)
accounts['hunter'] = (hunter, secrets.token_urlsafe(24))
subprocess.run(['docker', 'compose', '-p', moradon_stack.PROJECT, 'exec', '-T', 'server', 'n3e-server',
                'account-create', hunter], input=accounts['hunter'][1] + '\n', text=True, env=env,
               capture_output=True, check=True)
h = peer('hunter')
track_attack(h)
h.pump(.3)
bare = h.attacks[-1]  # PQ-422: the derived attack before the bow is worn
# PQ-434: the server grants each grade at its package durability (ItemStack
# field 4).
granted = {first(fields(r), 2).decode(): first(fields(r), 4) for r in bag(h)[5] if first(fields(r), 2)}
assert {i: granted.get(i) for i in GRADES} == {i: d + e for i, (_, _, d, e) in GRADE_STATS.items()}, granted
_, hunter_at = equip(h)
assert arrows(h) == ARROWS['starting'], arrows(h)
for x, z in provenance['features']['worm'][0]['route']:
    run(h, x, z)
# PQ-416: the bow strikes from range. First the hunter shoots the farthest
# worm in view between 8 m and 4 m inside the ranged limit (3-D) from where it
# stands (stepping back from the nearest worm when none is), and must not have
# moved for it; then it walks only while the nearest worm is beyond the limit.
spot = lambda e: (first(e, 3), first(e, 4), first(e, 5))  # noqa: E731
far, deadline = None, time.monotonic() + 60
while far is None and time.monotonic() < deadline:
    h.pump(.2)
    me = h.entities[h.id]
    worms = prey(h)
    reach = [e for e in worms if 8 < math.dist(spot(e), spot(me)) < LIMIT - 4]
    if not reach:
        if worms:
            near = min(worms, key=lambda e: math.dist(spot(e), spot(me)))
            d = max(.1, math.hypot(first(me, 3) - first(near, 3), first(me, 5) - first(near, 5)))
            run(h, first(near, 3) + (first(me, 3) - first(near, 3)) / d * 15,
                first(near, 5) + (first(me, 5) - first(near, 5)) / d * 15, tolerance=.5, seconds=20)
        continue
    target = max(reach, key=lambda e: math.dist(spot(e), spot(me)))
    before, d = spot(me), math.dist(spot(target), spot(me))
    # PQ-420: the shot's start event, its release (PQ-439) and its landing,
    # gathered while it flies (the start leaves the 40-tick event history
    # before a long flight lands).
    h.action_seq += 1
    h.send(15, integer(1, h.session) + integer(2, h.action_seq) + integer(3, first(target, 1)) + blob(4, h.action_id))
    events, result, end = {}, None, time.monotonic() + 6
    while result is None or time.monotonic() < end:
        assert time.monotonic() < end + 6, ('no result', h.action_seq)
        tag, data = h.receive()
        if tag == 10:
            events.update({first(e, 1): e for e in map(fields, data.get(14, []))})
        if tag == 16 and first(data, 1) == h.action_seq:
            result, end = first(data, 2, b'').decode(), time.monotonic() + .5
    if result in ('hit', 'miss'):
        cast = {first(e, 5): first(e, 2) for e in events.values() if first(e, 17) == h.action_seq and first(e, 3) == h.id}
        release = [e for e in events.values() if first(e, 17) == h.action_seq and first(e, 5) == 7]
        assert set(cast) == {2, 6, 7} and cast[7] - cast[2] == LAND, (cast, events)
        fly = flight_ticks(release[0])
        assert fly <= cast[6] - cast[7] <= fly + 20, (cast, fly)
        far = (round(d, 2), round(math.dist(spot(h.entities[h.id]), before), 3), cast[7] - cast[2], cast[6] - cast[7], fly)
assert far and far[0] > 8 and far[1] < .01, far
far_at, idle = time.monotonic(), {'paced': 0.0, 'top': 0.0}
print(f"PASS the bow strikes from range (1298 archery, PQ-416): a worm {far[0]} m away (melee reach {MELEE} m, "
      f"ranged limit {LIMIT} m) struck with the hunter standing still ({far[1]} m); the shot was released {far[2]} "
      f"ticks after its start ({LAND} to the stretched clip's marker, PQ-420) and landed {far[3]} ticks later, "
      f"when its arrow arrived ({far[4]} ticks at 77 m/s, PQ-439)", flush=True)
strikes, statuses, deadline = [], {}, time.monotonic() + 60
landed = []  # PQ-422: (result, damage, the hunter's derived attack) of each landed paced shot
flying = {}  # PQ-439: a released paced shot's sequence -> where its attacks start in h.attacks
cancelled = []  # PQ-439: released paced shots whose worm died in flight (PQ-444: arrow spent at the release)
unreleased = []  # PQ-439: accepted paced shots cancelled before their release (no arrow spent)
tries = []  # every paced try's status in order (accepted ones with their strike tick)
aimed = 0  # the worm the last released paced shot flies at
LOOP = 'paced'  # PQ-437: the loop whose wait for an area-0 worm `idle` counts
shot = first(h.entities[h.id], 10)  # the far shot's strike tick
while len(strikes) < 4 and time.monotonic() < deadline:
    worms = prey(h)
    if not worms:
        waited = time.monotonic()
        h.pump(.05)
        idle[LOOP] += time.monotonic() - waited
        continue
    me = h.entities[h.id]
    # PQ-439: while an arrow flies at a worm (which it may kill on arrival,
    # after the interval has run) the hunter takes another worm in reach if
    # there is one, so the pacing measures the interval, not a retarget.
    others = [e for e in worms if first(e, 1) != aimed and math.dist(spot(e), spot(me)) <= LIMIT - 4]
    target = min(others or worms, key=lambda e: math.dist(spot(e), spot(me)))
    if math.dist(spot(target), spot(me)) > LIMIT - 4:
        run(h, first(target, 3) - 6, first(target, 5), tolerance=.3)
        continue
    seen = max(0, len(h.attacks) - 1)
    result, damage = strike(h, first(target, 1), released=True)
    if result == 'released':
        aimed = first(target, 1)
    statuses[result] = statuses.get(result, 0) + 1
    tries.append(result if h.action_seq not in h.__dict__.get('casts', {}) else 'accepted@%d' % h.casts[h.action_seq][0])
    # Every accepted shot (its cast shown in the hunter's strike fields)
    # counts for the pacing, also one whose worm another arrow killed before
    # its release (PQ-439: the next cast may start while an arrow flies).
    if h.action_seq in h.__dict__.get('casts', {}):
        strikes.append(h.casts[h.action_seq])
        if result not in ('released', 'hit', 'miss'):
            unreleased.append((h.action_seq, result))  # cancelled before its release: no arrow
    if result == 'released':
        # PQ-439 (D-223): accepted and released; its result comes when its
        # arrow arrives, while the hunter already tries again.
        flying[h.action_seq] = seen
    elif result in ('hit', 'miss'):
        # The attack in effect from the send to the result (a kill's level
        # can raise it meanwhile).
        landed.append((result, damage, tuple(sorted(set(h.attacks[seen:])))))
for seq_, seen in flying.items():
    result, damage = result_of(h, seq_)
    assert result in ('hit', 'miss', 'target_dead', 'stale_target'), (seq_, result)
    if result in ('hit', 'miss'):
        landed.append((result, damage, tuple(sorted(set(h.attacks[seen:])))))
    else:
        cancelled.append(seq_)  # the worm died (another shot) while the arrow flew
# PQ-421: the far shot and each paced one spent an arrow, the refused tries none.
# PQ-444 (D-224): at its release, so one cancelled in flight spent it too; one
# cancelled before its release spent none. A shot whose worm died while its
# arrow write committed fails at once with its strike fields released: its
# arrow is spent, though its result may come before those fields show.
unreleased = [u for u in unreleased if u[0] not in h.__dict__.get('released', set())]
left = arrows(h)
assert left == ARROWS['starting'] - 1 - len(strikes) + len(unreleased), \
    (left, strikes, statuses, cancelled, unreleased)
# PQ-434 (D-221): the reverse +30 (attack 116 + 84) swapped in for the plain
# bow with no shot between must raise the hunter's derived attack, and its
# landed shots must deal the archery damage of that attack.
h.pump(.3)
with_base = h.attacks[-1]
s = bag(h)
s = bag(h, 6, LEFT, hunter_at, s)
wait(h, 10, lambda _: keys(h) == [])
bag(h, 5, next(i for i, r in enumerate(s[5]) if first(fields(r), 2) == TOP.encode()), LEFT, s)
wait(h, 10, lambda _: keys(h) == [KEYS[TOP]])
deadline = time.monotonic() + 8
while h.attacks[-1] in (bare, with_base) and time.monotonic() < deadline:
    h.pump(.1)
with_top = h.attacks[-1]
assert with_top > with_base > bare, (bare, with_base, with_top, h.attacks[-10:])
landed_top, deadline = [], time.monotonic() + 60
LOOP, top_from, top_alive = 'top', round(time.monotonic() - far_at, 1), len(prey(h))
while len(landed_top) < 2 and time.monotonic() < deadline:
    worms = prey(h)
    if not worms:
        waited = time.monotonic()
        h.pump(.05)
        idle[LOOP] += time.monotonic() - waited
        continue
    me = h.entities[h.id]
    target = min(worms, key=lambda e: math.dist(spot(e), spot(me)))
    if math.dist(spot(target), spot(me)) > LIMIT - 4:
        run(h, first(target, 3) - 6, first(target, 5), tolerance=.3)
        continue
    seen = max(0, len(h.attacks) - 1)
    result, damage = strike(h, first(target, 1))
    if result in ('hit', 'miss'):
        landed_top.append((result, damage, tuple(sorted(set(h.attacks[seen:])))))
h.logout()
print(f"PQ-437 hunt in worm area 0: the paced loop waited {idle['paced']:.1f} s for a live worm there; the swapped-bow "
      f"loop began {top_from} s after the far shot with {top_alive} alive and waited {idle['top']:.1f} s", flush=True)
print(f"PASS each released bow shot spent one of 1298's arrows at its release (PQ-421, PQ-444): {ARROWS['starting']} granted, "
      f"{1 + len(strikes)} shots ({len(cancelled)} cancelled in flight, {len(unreleased)} before their release), "
      f"{left} left "
      f"({sum(statuses.values()) - len(strikes)} refused tries spent none)", flush=True)
# PQ-422 (D-219): the bow's attack (2145 Item_Org column 16) under the bow
# stats category, and 1298's archery damage for it.
hit = recipe['ranged_attack']['profiles'][0]['skill_hit']
assert hit == dict(hit_rate=100, add_damage=100, add_damage_plus=0), hit
bow_stats = next(i for i in recipe['stats']['items'] if i['id'] == AZAGAI.decode())
assert (bow_stats['category'], bow_stats['attack']) == ('demo:weapon/bow', 116), bow_stats
defense = recipe['damage']['npc']['defense']
bounds = [(r, d, attacks, [archery_damage(a, defense, hit) for a in attacks]) for r, d, attacks in landed]
assert landed and all(attacks and min(attacks) > bare and (
    (r == 'hit' and any(lo <= d <= hi for lo, hi in ranges)) or (r == 'miss' and d == 0))
    for r, d, attacks, ranges in bounds), bounds
print(f"PQ-422 archery shots (result, damage, the hunter's derived attack from the send to the result, its (lowest, "
      f"highest) hit): {bounds}", flush=True)
print(f"PASS the bow's shots deal 1298's archery damage (PQ-422, AI 0040d471 -> 00443a34; MAGIC_TYPE2 108003: HitRate "
      f"100, AddDamage 100, AddDamagePlus 0): the Azagai's attack 116 under the bow category gives the hunter a derived "
      f"attack of {sorted({a for _, _, attacks in landed for a in attacks})} (bare-handed {bare}); against NPC defence "
      f"{defense} each of its {len(landed)} landed shots is a miss for 0 or a hit within the type-2 bounds of its "
      f"attack", flush=True)
# PQ-434 (D-221): the reverse +30's shots, at its own derived attack.
top_bounds = [(r, d, attacks, [archery_damage(a, defense, hit) for a in attacks]) for r, d, attacks in landed_top]
assert len(landed_top) == 2 and all(attacks and min(attacks) >= with_top and (
    (r == 'hit' and any(lo <= d <= hi for lo, hi in ranges)) or (r == 'miss' and d == 0))
    for r, d, attacks, ranges in top_bounds), top_bounds
print(f"PQ-434 reverse +30 shots (result, damage, the hunter's derived attack, its (lowest, highest) hit): "
      f"{top_bounds}", flush=True)
print(f"PASS the reverse +30's upgrade attack reaches the server (PQ-434, D-221): swapped in for the plain Azagai with "
      f"no shot between, its attack 200 (116 + Item_Ext column 9's 84) raises the hunter's derived attack from "
      f"{with_base} to {with_top} (bare-handed {bare}), and its {len(landed_top)} landed shots are each a miss for 0 or "
      f"a hit within the type-2 bounds of that attack", flush=True)
gaps = [b2 - b1 for (b1, _), (b2, _) in zip(strikes, strikes[1:])]
assert len(strikes) >= 3 and all(s == BOW for _, s in strikes), (strikes, statuses)
assert statuses.get('cooldown', 0) > 0 and all(g >= 29 for g in gaps) and min(gaps) <= 30, (gaps, statuses, tries)
print(f"PASS the server paces the bow at its 1298 interval: accepted strikes {gaps} ticks apart (at least 29 = "
      f"ceiling(1450 / 50), the closest at most a tick over), the earlier tries refused as cooldown "
      f"({statuses.get('cooldown')}), each frozen with the bow's style {BOW}; statuses {statuses}, tries in order "
      f"{tries}", flush=True)
if os.environ.get('N3E_GRAPHICAL') != '1':
    b.logout()
    sys.exit(0)


def bow_clips():
    """PQ-347, the drawn clips: the test client logs in as a fourth account
    wearing the bow at the worms, presses Z (the nearest worm: the ready
    stance) and then R (the attack toggle); once it has shot, a fifth (the
    striker, fresh, so the worms' retaliation has not worn it down) strikes a
    worm over the wire. The client's own and the striker's drawn combat clips
    (WEARER_CLIP, from the plug's wearer) must be the bow profile's: ready 92
    and the shot 26 for itself, the shot for the striker, and never an unarmed
    clip (86, 87, 88 or the empty hands' moving 15). PQ-423: on both, each
    shot's start draws the cast effect (the archery row's self FX 500) on
    joint 12, turned with the archer's facing, ended at once when the shot
    lands or is cancelled; the client captures its first draw (before and
    after the effect pass)."""
    index = {clip(i): i for i in range(len(combat['clips']))}
    ready, shot = index['player-combat-92.bin'], index['player-combat-26.bin']
    unarmed = {index['player-combat-%d.bin' % n] for n in (86, 87, 88, 15)}
    for role in ('striker', 'spotter'):
        name = 'plug' + role[:4] + secrets.token_hex(5)
        accounts[role] = (name, secrets.token_urlsafe(24))
        subprocess.run(['docker', 'compose', '-p', moradon_stack.PROJECT, 'exec', '-T', 'server', 'n3e-server',
                        'account-create', name], input=accounts[role][1] + '\n', text=True, env=env,
                       capture_output=True, check=True)
    h = peer('striker')
    equip(h)
    for x, z in provenance['features']['worm'][0]['route']:
        run(h, x, z)
    q = peer('spotter')
    equip(q)
    for x, z in provenance['features']['worm'][0]['route']:
        run(q, x, z)
    q.logout()
    lines, hits = [], 0
    account, password = accounts['spotter']
    with tempfile.TemporaryDirectory(dir=root / 'build') as config:
        proc = subprocess.Popen(
            ['build/client/n3e-test-client', str(package), '--connect', 'localhost:' + str(state['port']), '--ca',
             'deploy/local/ca.pem', '--auto-login', '--fixed-window', '1280x1024', '--world-smoke', '20',
             '--capture', str(OUT / 'bow-clips.ppm')],
            env={**env, 'N3E_TEST_ACCOUNT': account, 'N3E_TEST_PASSWORD': password, 'N3E_TEST_ATTACHMENTS': '1',
                 'N3E_TEST_CAMERA': '0 0 0.5 9', 'N3E_TEST_SHOWCASE_TARGET': '2.0',
                 'N3E_TEST_SHOWCASE_ATTACK': '3.0', 'XDG_CONFIG_HOME': config, 'N3E_TEST_EFFECTS': '1'},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        reader = threading.Thread(target=lambda: lines.extend(proc.stdout), daemon=True)
        reader.start()
        end = time.monotonic() + 120
        unreachable = set()
        # The striker waits for the client's own shot, so its strikes cannot
        # kill the worm the client has selected before it shoots.
        shot_line = re.compile(r'^WEARER_CLIP entity=\d+ self=1 entry=\d+ combat=%d ' % shot, re.M)
        while proc.poll() is None and time.monotonic() < end:
            worms = [e for e in h.entities.values() if first(e, 9) and first(e, 7) and first(e, 1) not in unreachable]
            if worms and shot_line.search(''.join(lines)):
                me = h.entities[h.id]
                target = min(worms, key=lambda e: math.hypot(first(e, 3) - first(me, 3), first(e, 5) - first(me, 5)))
                try:
                    if math.hypot(first(target, 3) - first(me, 3), first(target, 5) - first(me, 5)) > 1:
                        run(h, first(target, 3) - .6, first(target, 5), tolerance=.3, seconds=6)
                    hits += h.action(first(target, 1)) in ('hit', 'miss')
                except AssertionError:  # a worm the striker cannot walk to: take another
                    h.move(0, 0)
                    unreachable.add(first(target, 1))
            h.pump(.2)
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        reader.join(10)
    text = ''.join(lines)
    (OUT / 'bow-clips.log').write_text(text)
    h.logout()
    exited(proc.returncode, text)
    nearest = re.search(r'^SHOWCASE_TARGET at=\S+ nearest=(\d+)$', text, re.M)
    assert nearest and int(nearest[1]) and re.search(r'^SHOWCASE_ATTACK at=\S+ target=[1-9]', text, re.M), text[-2000:]
    drawn = [(int(e), int(s), int(c), int(st)) for e, s, c, st in
             re.findall(r'^WEARER_CLIP entity=(\d+) self=(\d) entry=\d+ combat=(-?\d+) state=\d+ cast=-?\d+ '
                        r'style=(\d+) strike_style=\d+$', text, re.M)]
    mine = [c for e, s, c, _ in drawn if s == 1]
    others = [c for e, s, c, _ in drawn if e == h.id]
    assert all(st == BOW for e, s, _, st in drawn if e == h.id or s == 1), drawn
    assert ready in mine and shot in mine and not unarmed & set(mine), (mine, ready, shot, unarmed)
    assert shot in others and not unarmed & set(others), (others, shot, unarmed)
    print(f"PASS Moradon client draws the bow's clips: after Z its own ready stance is combat clip {ready} "
          f"(player-combat-92.bin) and after R its shot {shot} (player-combat-26.bin); the striker's strikes "
          f"({hits} accepted) draw {shot} for the observer; no unarmed clip ({sorted(unarmed)}) on either; "
          f"{OUT / 'bow-clips.log'}", flush=True)
    cast_effect(text, h.id)


def cast_effect(text, striker):
    """PQ-423 (D-220): the archery row's self FX on the archer, drawn by its
    own client and by an observer. 1298's cast start 00583f20 (an observer's
    casting phase 00585a90) triggers FX 500 on part 12 (00479de0), the bundle
    faces the caster's +Z (00477590) and the release stops it at once
    (00584b00 -> 0047a710)."""
    key = recipe['ranged_attack']['profiles'][0]['cast_effect']
    assert key == dict(clip='ranged-cast-500', joints=[12]), key
    starts = {(int(a), int(s_), int(t)): int(r) for a, s_, t, r in re.findall(
        r'^RANGED_CAST_FX start actor=(\d+) self=(\d) tick=(\d+) request=(\d+) joint=12 age=\S+$', text, re.M)}
    # The release event of each shot (kind 7 since PQ-439, by actor and
    # request), where 1298's 00584b00 stops the self FX.
    landed = {(int(a), int(r)): int(t) for a, r, t in re.findall(
        r'^RANGED_RELEASED actor=(\d+) self=\d request=(\d+) tick=(\d+) hit=0$', text, re.M)}
    stops = {(int(a), int(s_), int(t)): float(g) for a, s_, t, g in re.findall(
        r'^RANGED_CAST_FX stop actor=(\d+) self=(\d) tick=(\d+) joint=12 age=(\S+)$', text, re.M)}
    draws = [(int(a), int(s_), float(hd), [float(v) for v in o.split(',')], [float(v) for v in b.split(',')])
             for a, s_, hd, o, b in re.findall(r'^RANGED_CAST_FX draw actor=(\d+) self=(\d) tick=\d+ joint=12 '
                                               r'vertices=\d+ heading=(\S+) offset=(\S+) base=(\S+)$', text, re.M)]
    # PQ-435: the client's world smoke ends on its own clock (WORLD tick=,
    # the last snapshot tick it applied, printed once as it ends) while the
    # archers keep shooting, so a shot that starts near the end can have had
    # neither its landing nor a cancel reach the client. The bounds below let
    # a stop come up to LAND ticks plus 0.6 s (12 ticks) after its start; only
    # an actor's last start, with no stop, whose bound the client's final
    # tick had not reached is left unchecked. Any other start without a stop
    # still fails.
    final = re.search(r'^WORLD tick=(\d+) ', text, re.M)
    assert final, text[-2000:]
    final = int(final[1])
    last = {}
    for k in starts:
        last[k[:2]] = max(last.get(k[:2], 0), k[2])
    cut = {k for k in starts if k not in stops and k[2] == last[k[:2]] and final < k[2] + LAND + 12}
    mine = [k for k in starts if k[1] == 1 and k not in cut]
    seen = [k for k in starts if k[0] == striker and k[1] == 0 and k not in cut]
    assert mine and seen, (sorted(starts), sorted(cut), final, striker, text[-2000:])
    # The bundle lives 10 s. A shot that landed ends its effect at the
    # landing: its gap from the start event in ticks, give or take the local
    # start's lead and a snapshot's delay (as tests/ranged_attack_live.py);
    # one that did not land (a cancel: the striker moves between worms) ends
    # no later than a landing would (LAND, 27 ticks, plus that delay).
    ended = [stops[k] for k in mine + seen if k in stops]
    at_landing = []
    for k in mine + seen:
        assert k in stops, (k, stops)
        land = landed.get((k[0], starts[k]))
        if land is not None:
            gap = (land - k[2]) * .05
            assert gap - .15 <= stops[k] <= gap + .6, (k, stops[k], gap)
            at_landing.append(round(stops[k], 2))
        else:
            assert 0 <= stops[k] <= LAND * .05 + .6, (k, stops[k])
    assert at_landing, (starts, landed, stops)
    # PQ-430 (D-220, corrected by PQ-429): the mesh part's init 0048ea70 puts
    # the arrow's shape at the bundle position at the clone (0) plus the
    # part's file position ((0, 0, 0) in arrow.fxb), not at the shape file's
    # (1.782, 3.721, -0.409); the rig draws it in the drawing hand. So the
    # clip's centroid is the arrow mesh's own: at the joint's height, on its
    # axis, ahead of it along the archer's facing (KO +z, n3e -z; the arrow
    # reaches about 0.89 m ahead and 0.08 m behind, centroid about 0.34 m).
    for _, _, hd, offset, base in draws:
        turned = (base[0] * math.cos(hd) + base[2] * math.sin(hd), base[1], -base[0] * math.sin(hd) + base[2] * math.cos(hd))
        assert all(abs(a - b) < 1e-3 for a, b in zip(offset, turned)), (offset, turned, hd)
        assert abs(base[0]) < .1 and abs(base[1]) < .1 and -.9 < base[2] < 0, base
    assert {s_ for _, s_, _, _, _ in draws} == {0, 1}, draws
    made = OUT / 'bow-clips.ppm.effect-ranged-cast-500'
    before, after = (pathlib.Path(str(made) + x) for x in ('.before.ppm', '.after.ppm'))
    assert before.is_file() and after.is_file(), sorted(p.name for p in OUT.iterdir())
    w, h_, a_pixels = npc_looks_live.read_ppm(after)
    _, _, b_pixels = npc_looks_live.read_ppm(before)
    changed = sum(a_pixels[i:i + 3] != b_pixels[i:i + 3] for i in range(0, len(a_pixels), 3))
    for ppm, pixels in ((before, b_pixels), (after, a_pixels)):
        png(ppm.with_suffix('.png'), w, h_, [pixels[y * w * 3:(y + 1) * w * 3] for y in range(h_)])
    print(f"PASS Moradon client draws 1298's archery cast effect (PQ-423): FX 500 (the arrow, fx/arrow.fxb) on joint "
          f"12 from the shot's start, for its own shots ({len(mine)}) and the striker's as an observer ({len(seen)}); "
          f"ended at once {sorted(round(g, 2) for g in ended)} s in, {len(at_landing)} of them at their shot's "
          f"release event (RANGED_RELEASED; the rest no later, a cancel; the bundle would live 10 s); "
          f"{len(cut)} last shot(s) {sorted(cut)} left unchecked, started too close to the client's final tick {final} "
          f"for a stop within those bounds (PQ-435); drawn at the joint plus the arrow turned by the archer's facing "
          f"({len(draws)} draws; the arrow's "
          f"centroid {draws[0][4]} in the archer's frame, at the joint and ahead of it, PQ-430: the part's position, "
          f"not the shape file's); {changed} pixels differ around its first draw "
          f"({after.with_suffix('.png')})", flush=True)
    arrow_flight(text, striker, final)


def turn_to(d):
    """D-222: the shortest turn from the model's forward (0, 0, -1) to the
    unit `d` (render/effects.h flight_rotation), as a function of a point."""
    c, kx, ky = -d[2], d[1], -d[0]
    s_ = math.hypot(kx, ky)
    if s_ < 1e-6:
        return (lambda v: v) if c > 0 else (lambda v: (-v[0], v[1], -v[2]))
    kx, ky, t = kx / s_, ky / s_, 1 - c
    m = [[c + kx * kx * t, kx * ky * t, ky * s_], [kx * ky * t, c + ky * ky * t, -kx * s_], [-ky * s_, kx * s_, c]]
    return lambda v: tuple(sum(m[r][k] * v[k] for k in range(3)) for r in range(3))


def arrow_flight(text, striker, final):
    """PQ-417 (D-222): the archery row's flying FX 590 from the archer's part
    12 to the worm's box at 77 m/s, then its target FX 550 on the worm, drawn
    by the archer's own client and by an observer of the striker. 1298's
    release 00584b00 (an observer's flying receive 00585f20) calls 00587ac0,
    which flies FX 590 with move type 0 (0047a2d0; 00477590 moves it along
    its direction, pitch included, at the bundle's velocity; 0048f700 turns
    the arrow to it); 0047a8d0 stops it at the target's box and the -101
    receive 00586fa0 triggers FX 550 at the target's part. PQ-445: the
    shooter's own client flies its arrow at its own release (00585830 ->
    00584b00 at the clip's marker), the observer at the flying packet."""
    # PQ-439 (D-223): the flight launches at the release event (kind 7);
    # PQ-445 (D-226): the archer's own client launches its own at the
    # predicted release (RANGED_FLIGHT local, by request), which that event
    # confirms (RANGED_FLIGHT confirm) without a second flight. Flights are
    # keyed ('own', request) and ('seen', actor, tick).
    num = lambda v: [float(x) for x in v.split(',')]
    landed = {(int(a), int(s_), int(r)): int(t) for a, s_, r, t in re.findall(
        r'^RANGED_RELEASED actor=(\d+) self=(\d) request=(\d+) tick=(\d+) hit=0$', text, re.M)}
    started = {}
    for a, s_, t, r, g, f, d, sp, ln, b in re.findall(
            r'^RANGED_FLIGHT start actor=(\d+) self=(\d) tick=(\d+) request=(\d+) target=\d+ hit=[01] age=(\S+) '
            r'from=(\S+) dir=(\S+) speed=(\S+) launch=(\S+) box=([01])$', text, re.M):
        key = ('own', int(r)) if s_ == '1' else ('seen', int(a), int(t))
        started[key] = (num(f), num(d), float(sp), float(ln), int(b), float(g), int(t))
    local = {}
    # `late`: how long after the predicted release the launching frame came;
    # the flight starts at that frame (`age` 0).
    for r, g, lt, f, d, sp, ln, b in re.findall(
            r'^RANGED_FLIGHT local actor=\d+ self=1 request=(\d+) target=\d+ age=(\S+) predicted=\S+ late=(\S+) '
            r'from=(\S+) dir=(\S+) speed=(\S+) launch=(\S+) box=([01])$', text, re.M):
        assert 0 <= float(lt) < .1 and float(g) == 0, (r, lt, g)
        local[('own', int(r))] = (num(f), num(d), float(sp), float(ln), int(b), float(g), 0)
    confirmed = {('own', int(r)): int(t) for r, t in re.findall(
        r'^RANGED_FLIGHT confirm actor=\d+ self=1 request=(\d+) tick=(\d+) lead=\S+ held=\d+$', text, re.M)}
    cancelled = {('own', int(r)) for r in re.findall(
        r'^RANGED_FLIGHT cancel actor=\d+ self=1 request=(\d+) age=\S+ held=[01]$', text, re.M)}
    assert not set(local) & set(started), (sorted(local), sorted(started))
    started.update(local)

    def key_of(a, s_, t, r):
        return ('own', int(r)) if s_ == '1' else ('seen', int(a), int(t))
    drawn = [(key_of(a, s_, t, r), float(g), num(an), num(o), num(b))
             for a, s_, t, r, g, an, o, b in re.findall(
                 r'^RANGED_FLIGHT draw actor=(\d+) self=(\d) tick=(\d+) request=(\d+) age=(\S+) vertices=\d+ '
                 r'anchor=(\S+) offset=(\S+) base=(\S+)$', text, re.M)]
    hits = {key_of(a, s_, t, r): (float(re_), float(late), int(b), c, int(j))
            for a, s_, t, r, re_, late, b, c, j in re.findall(
                r'^RANGED_FLIGHT hit actor=(\d+) self=(\d) tick=(\d+) request=(\d+) target=\d+ reach=(\S+) late=(\S+) '
                r'held=\S+ at=\S+ box=([01]) clip=(\S+) joint=(-?\d+)$', text, re.M)}
    # Every release launches a flight: an observed one at its event, an own
    # one at its prediction confirmed by its event (or at the event, when the
    # prediction found its target undrawn).
    seen_released = {('seen', a, t) for (a, s_, _), t in landed.items() if s_ == 0}
    own_released = {('own', r): t for (_, s_, r), t in landed.items() if s_ == 1}
    assert {k for k in started if k[0] == 'seen'} == seen_released, (sorted(seen_released), sorted(started))
    for k, t in own_released.items():
        assert k in started and (confirmed.get(k) == t or (k not in local and started[k][6] == t)), (k, t, confirmed)
    # A prediction is confirmed by its release or ended by the shot's refusal
    # or cancel; only one launched in the client's last 0.6 s may be neither.
    assert not set(confirmed) & cancelled and set(confirmed) <= set(local), (sorted(confirmed), sorted(cancelled))
    mine = [k for k in started if k[0] == 'own']
    seen = [k for k in started if k[0] == 'seen' and k[1] == striker]
    assert mine and seen, (sorted(started), striker)
    for k, (origin, d, speed, launch, box, _, _) in started.items():
        assert speed == 77 and box == 1 and abs(math.hypot(*d) - 1) < 1e-3 and 0 < launch <= 45, (k, started[k])
    # Drawn at its start plus the direction x speed x age, the arrow turned
    # from -z to the direction, its centroid the arrow mesh's own (PQ-430).
    # At 77 m/s a worm a metre or two away is reached in 15-30 ms: an
    # observer's arrow, launched at the release event (a snapshot late), is
    # often never drawn, so only a flight with 0.1 s or more left at its
    # launch must be drawn (the default suite's 4 m/s arrow is drawn on every
    # shot).
    assert {k for k, *_ in drawn} <= set(started), drawn
    for k, age, anchor, offset, base in drawn:
        origin, d, speed = started[k][:3]
        assert all(abs(anchor[i] - (origin[i] + d[i] * speed * age)) < 1e-3 for i in range(3)), (k, anchor, origin, d)
        turned = turn_to(d)(base)
        assert all(abs(a - b) < 1e-3 for a, b in zip(offset, turned)), (k, offset, turned, d)
        assert abs(base[0]) < .1 and abs(base[1]) < .1 and -.9 < base[2] < 0, base
    pitch = max(abs(v[1][1]) for v in started.values())
    # Each flight ends where its ray enters the worm's box, with FX 550 on the
    # worm's joint 0; one launched in the client's last frames may not have,
    # nor a prediction the server did not release (cancelled).
    unfinished = {k for k in started if k not in hits and k not in cancelled}
    newest = max(mine)
    for k in unfinished:
        if k[0] == 'own' and k in local and k not in confirmed:
            assert k == newest, (k, newest)  # its release not yet seen when the client ended
        else:
            tick = k[2] if k[0] == 'seen' else confirmed.get(k, started[k][6])
            assert tick * .05 + .6 >= final * .05, (k, tick, final)
    for k, (reach, late, box, clip_, joint) in hits.items():
        assert box == 1 and 0 < reach < started[k][3] and clip_ == 'ranged-hit-550' and joint == 0, (k, hits[k])
        assert -1e-3 <= late < .25, (k, late)
    long_ = {k for k in hits if hits[k][0] / started[k][2] - started[k][5] >= .1}
    assert long_ <= {k for k, *_ in drawn}, (sorted(long_), drawn)
    pairs = {}
    for clip_ in ('ranged-flight-590', 'ranged-hit-550'):
        if clip_ == 'ranged-flight-590' and not drawn:
            continue  # no flight was in the air for a drawn frame
        made = OUT / ('bow-clips.ppm.effect-' + clip_)
        before, after = (pathlib.Path(str(made) + x) for x in ('.before.ppm', '.after.ppm'))
        assert before.is_file() and after.is_file(), (clip_, sorted(p.name for p in OUT.iterdir()))
        w, h_, a_pixels = npc_looks_live.read_ppm(after)
        _, _, b_pixels = npc_looks_live.read_ppm(before)
        pairs[clip_] = sum(a_pixels[i:i + 3] != b_pixels[i:i + 3] for i in range(0, len(a_pixels), 3))
        for ppm, pixels in ((before, b_pixels), (after, a_pixels)):
            png(ppm.with_suffix('.png'), w, h_, [pixels[y * w * 3:(y + 1) * w * 3] for y in range(h_)])
        assert pairs[clip_] > 0, (clip_, pairs)
    shown = (f"drawn at its start plus the direction x speed x age and turned from -z to the direction "
             f"({len(drawn)} draws, {len(long_)} flights with 0.1 s or more left at launch)" if drawn else
             f"no flight was in the air for a drawn frame ({len(long_)} with 0.1 s or more left at launch; drawing "
             f"checked in ranged_attack_live)")
    print(f"PASS Moradon client flies 1298's archery arrow (PQ-417, PQ-445): FX 590 from joint 12 at 77 m/s at each "
          f"release ({len(mine)} own shots, {len([k for k in mine if k in local])} at the predicted release, RANGED_FLIGHT "
          f"local, {len([k for k in mine if k in confirmed])} confirmed by their release event and {len(cancelled & set(mine))} "
          f"ended unreleased; {len(seen)} of the striker's as an observer at its release event, RANGED_FLIGHT start), {shown}; "
          f"directions pitched up "
          f"to {pitch:.3f}, ending where its ray enters the worm's box ({len(hits)} flights, "
          f"{sorted(round(v[0], 2) for v in hits.values())} m) with FX 550 (fx/blow.fxb) on the worm's joint 0; "
          f"{len(unfinished)} launched at the client's end unfinished; pixels differ around the first draws: "
          f"{pairs}", flush=True)


OUT.mkdir(parents=True, exist_ok=True)
bow_clips()

OUT.mkdir(parents=True, exist_ok=True)
capture = OUT / 'azagai.ppm'
heal = recipe['skills']['skills'][0]['id']
lines = []
account, password = accounts['archer']
with tempfile.TemporaryDirectory(dir=root / 'build') as config:
    proc = subprocess.Popen(
        ['build/client/n3e-test-client', str(package), '--connect', 'localhost:' + str(state['port']), '--ca',
         'deploy/local/ca.pem', '--auto-login', '--fixed-window', '1280x1024', '--world-smoke', '20',
         '--capture', str(capture)],
        env={**env, 'N3E_TEST_ACCOUNT': account, 'N3E_TEST_PASSWORD': password, 'N3E_TEST_ATTACHMENTS': '1',
             'N3E_TEST_ATTACHMENT_CAPTURES': f'{A},{B}', 'XDG_CONFIG_HOME': config},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    reader = threading.Thread(target=lambda: lines.extend(proc.stdout), daemon=True)
    reader.start()
    cast = None
    while proc.poll() is None:
        b.pump(.1)
        if cast is None and re.search(rf'^ATTACHMENT_CAPTURE at={B} ', ''.join(lines), re.M):
            # The companion casts Tiny Healing on itself (1.9 s): KO clip 17.
            cast = b.action(b.id, action=heal)
    reader.join(10)
text = ''.join(lines)
capture.with_suffix('.log').write_text(text)
exited(proc.returncode, text)
assert cast == 'cast_pending', (cast, text[-1500:])
# PQ-355: this run's captures and every glow run's share one view.
VIEW = capture_camera.SameView()
VIEW.check(capture.name, text)
other = b.id
start = rf'^ATTACHMENT entity=(\d+) self=(\d) key={KEY} entry=0 group=0 joint=7 vertices=(\d+) lit=0 modulate=1 emissive=0$'
drawn = {int(e): (int(s), int(v)) for e, s, v in re.findall(start, text, re.M)}
mine = [e for e, (s, _) in drawn.items() if s == 1]
assert len(mine) == 1 and other in drawn and len(drawn) == 2, (drawn, text[-2000:])
mine = mine[0]
samples = plug_samples(text)
report = {}
for wearer in (mine, other):
    got = [s for s in samples if s['entity'] == wearer]
    assert len(got) >= 6, (wearer, len(got), text[-2000:])
    assert {s['slot'] for s in got} == ({0} if wearer == mine else {0, 2}), (wearer, {s['slot'] for s in got})
    worst = max(math.dist(frame(s), s['placed']) for s in got)
    assert worst < 2e-3, (worst, got)
    breath = [s for s in got if s['slot'] == 0]
    times = sorted({round(s['time'], 2) for s in breath})
    # The skinned bow's box: breath bends the limbs and the string.
    moved = max(max(abs(x - y) for x, y in zip(s['bounds'], breath[0]['bounds'])) for s in breath)
    # The times as sampled: rounded to 0.01 s (for counting), a time near the
    # end of the 1.756 s clip can round past it (PQ-339 found 1.76).
    assert len(times) >= 4 and all(0 <= s['time'] <= entry['slots'][0]['duration'] + 1e-6 for s in breath), times
    assert moved > 2e-3, moved
    report[wearer] = dict(samples=len(got), times=len(times), moved=round(moved, 4), worst=worst)
magic = [s for s in samples if s['entity'] == other and s['slot'] == 2]
assert magic and all(0 <= s['time'] <= MAGIC['duration'] + 1e-6 for s in magic), magic
# Once and held (2233 0042e070 with the once flag): the cast's samples, in
# order, never go back, and the last is at the clip's end (frame 195). A
# looping clip would wrap back to the start within the 1.9 s cast.
held = [s['time'] for s in magic]
assert len(held) >= 2 and all(b >= a for a, b in zip(held, held[1:])) and abs(held[-1] - MAGIC['duration']) < 1e-4, \
    (held, MAGIC['duration'])
clips = re.findall(rf'^ATTACHMENT_CLIP entity={other} entry=0 clip=(\d)$', text, re.M)
assert clips == ['0', '2', '0'], clips
assert re.findall(rf'^ATTACHMENT_CLIP entity={mine} entry=0 clip=(\d)$', text, re.M) == ['0']
print(f"PASS Moradon client draws the skeletal Azagai on itself and on the other player on joint 7: every sampled "
      f"centre of its drawn vertices is the wearer x joint x placement of the skinned bow (worst "
      f"{max(r['worst'] for r in report.values()):.1e}); breath plays on its own clock "
      f"{[(r['samples'], r['times'], r['moved']) for r in report.values()]} (samples, distinct times, metres the "
      f"skinned box moved), and the other's Tiny Healing plays magic once ({len(magic)} samples at "
      f"{held} s, never back, the last at its {MAGIC['duration']:.4f} s end, frame 195, the last key) before breath "
      f"again", flush=True)
made = re.findall(r'^ATTACHMENT_CAPTURE at=([0-9.]+) drawn=[0-9.e+-]+ path=(.+)$', text, re.M)
assert [float(t) for t, _ in made] == [A, B], made
shown = [pathlib.Path(p) for _, p in made]
boxes = {}
for at in (A, B):
    for e, n, box in re.findall(rf'^ATTACHMENT_BOX at={at} entity=(\d+) self=\d entry=(\d+) box=(\S+)$', text, re.M):
        x0, y0, x1, y1 = (int(v) for v in box.split(','))
        old = boxes.get(int(e), (x0, y0, x1, y1))
        boxes[int(e)] = (min(old[0], x0), min(old[1], y0), max(old[2], x1), max(old[3], y1))
assert set(boxes) == {mine, other}, (boxes, mine, other)
shares = {e: round(share(shown[0], shown[1], box), 3) for e, box in boxes.items()}
assert min(shares.values()) >= SWING, (shares, boxes)
for ppm in shown:
    w, h, pixels = npc_looks_live.read_ppm(ppm)
    png(ppm.with_suffix('.png'), w, h, [pixels[y * w * 3:(y + 1) * w * 3] for y in range(h)])
# A 3x crop around both bows: breath at the two phases, side by side.
x0, y0 = max(0, min(v[0] for v in boxes.values()) - 40), max(0, min(v[1] for v in boxes.values()) - 40)
x1, y1 = min(w, max(v[2] for v in boxes.values()) + 40), min(h, max(v[3] for v in boxes.values()) + 40)
sources = [npc_looks_live.read_ppm(p)[2] for p in shown]
crop_rows = []
for y in range(y0, y1):
    row = b''
    for src in sources:
        row += b''.join(bytes(src[(y * w + x) * 3:(y * w + x) * 3 + 3]) * 3 for x in range(x0, x1))
    crop_rows += [row] * 3
crop = OUT / 'azagai-crop-two-phases.png'
png(crop, (x1 - x0) * 6, (y1 - y0) * 3, crop_rows)
digests = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (*shown, crop)}
print(f"PASS Moradon skeletal plug graphical: inside the Azagai boxes {[boxes[mine], boxes[other]]} "
      f"{[shares[mine], shares[other]]} of the pixels differ between {A} s and {B} s of breath; "
      f"captures {digests}", flush=True)
b.logout()


def icon_distance(capture, rect, mirror=False):
    """Mean absolute RGB difference between the slot's screen pixels and the
    icon's texels (UV 0..45/64 across the slot, 004c1430; nearest texel, 2 px
    in from the slot's edges), or their mirror image."""
    w, h, pixels = npc_looks_live.read_ppm(capture)
    tw, _, rgba = ICON_TEXELS
    x0, y0, x1, y1 = rect
    total = count = 0
    for y in range(math.ceil(y0) + 2, math.floor(y1) - 2):
        for x in range(math.ceil(x0) + 2, math.floor(x1) - 2):
            u = min(44, int((x + .5 - x0) / (x1 - x0) * 45))
            v = min(44, int((y + .5 - y0) / (y1 - y0) * 45))
            t = (v * tw + (44 - u if mirror else u)) * 4
            i = (y * w + x) * 3
            total += sum(abs(pixels[i + c] - rgba[t + c]) for c in range(3)) / 3
            count += 1
    assert count >= 200, (count, rect)
    return total / count, count


def inventory_view(where, item='demo:item/azagai'):
    """The client's inventory with `item` in the first account's left hand or
    in its bag: the slot draws the 2145 icon and its tooltip's head is the item's
    (LABELS, 005aa8e0's name with <selfname> replaced by the character's name,
    in its colour, and the kind line under it in its colour: HEADS, PQ-354)."""
    work = root / 'build/pq338/moradon/bag'
    work.mkdir(parents=True, exist_ok=True)
    grade = list(GRADES).index(item)
    label = LABELS[grade].replace('<selfname>', names['archer'])
    colour, lines = HEADS[grade]
    shot = work / ('%s-%s' % (item.split('/')[-1], where))
    account, password = accounts['archer']
    with tempfile.TemporaryDirectory(dir=root / 'build') as config:
        proc = subprocess.run(
            ['build/client/n3e-test-client', str(package), '--connect', 'localhost:' + str(state['port']), '--ca',
             'deploy/local/ca.pem', '--auto-login', '--fixed-window', '1280x1024', '--world-smoke', '60',
             '--capture', str(shot)],
            env={**env, 'N3E_TEST_ACCOUNT': account, 'N3E_TEST_PASSWORD': password, 'N3E_TEST_ITEM_TOOLTIP': 'azagai',
                 'N3E_TEST_ITEMS': 'azagai=' + item, 'XDG_CONFIG_HOME': config},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
    text = proc.stdout
    shot.with_suffix('.log').write_text(text)
    exited(proc.returncode, text, 2000)
    slot = re.findall(r'^ITEM_SLOT key=(%s:\d+) item=%s icon=(\d) rect=([0-9.e+-]+),([0-9.e+-]+),'
                      r'([0-9.e+-]+),([0-9.e+-]+)$' % (where, re.escape(item)), text, re.M)
    assert len(slot) == 1, text[-2000:]
    key, drawn, rect = slot[0][0], slot[0][1], tuple(float(v) for v in slot[0][2:])
    assert drawn == '1', ('no icon drawn', key)
    assert where == 'bag' or key == 'gear:%d' % LEFT, key
    rows = re.findall(r'^ITEM_TOOLTIP key=%s row=(\d+) text=(.*)$' % re.escape(key), text, re.M)
    assert rows and rows[0] == ('0', label), rows
    shots = {name: pathlib.Path(f'{shot}.item-{name}.ppm') for name in ('slot', 'tooltip')}
    assert all(s.stat().st_size > 0 for s in shots.values()), shots
    head, _ = tooltip_head.check(text, key, shots['tooltip'], [(label, colour)] + lines, base=shots['slot'])
    near, count = icon_distance(shots['slot'], rect)
    mirrored, _ = icon_distance(shots['slot'], rect, mirror=True)
    assert near < 16 and mirrored > 2 * near, (near, mirrored, count, rect)
    for ppm in shots.values():
        w, h, pixels = npc_looks_live.read_ppm(ppm)
        png(ppm.with_suffix('.png'), w, h, [pixels[y * w * 3:(y + 1) * w * 3] for y in range(h)])
    print(f"PASS Moradon client {'equipment slot' if where == 'gear' else 'bag'} draws {label} "
          f"with its 2145 icon: {key} at {rect} (mean RGB difference {near:.1f} over {count} texels, mirrored "
          f"{mirrored:.1f}), tooltip {[t for _, t in rows]}, its head drawn (row, colour, pixels of it, without the tooltip) {head}; "
          f"{shots['slot'].with_suffix('.png')}, {shots['tooltip'].with_suffix('.png')}", flush=True)


inventory_view('gear')
a = peer('archer', create=False)
s = bag(a)
s = bag(a, 6, LEFT, archer_at, s)
wait(a, 10, lambda _: keys(a) == [])
a.logout()
inventory_view('bag')


# PQ-337, PQ-350: the grades' glow on the skeletal plug. The first account
# wears the reverse +1 (a pulse at 1x), the second the reverse +30 (a steady
# light at 2x).
PEAK, TROUGH = 2.0, 10.75  # seconds of the local glow clock: the pulse held at 1, then at 0 (5.25 s into 5.5)
LIT = 0.06  # share of a bow box's pixels a glow must make 40 levels brighter than EquipmentGlow=0


def wear(p, item, held=None):
    """`item` into the left hand (the one held there back to bag slot
    `held` first); the bag slot it came from."""
    s = bag(p)
    if held is not None:
        s = bag(p, 6, LEFT, held, s)
        wait(p, 10, lambda _: keys(p) == [])
    at = next(i for i, r in enumerate(s[5]) if first(fields(r), 2) == item.encode())
    bag(p, 5, at, LEFT, s)
    wait(p, 10, lambda _: keys(p) == [KEYS[item]])
    return at


a = peer('archer', create=False)
low_at = wear(a, LOW)
a.logout()
inventory_view('gear', LOW)
b = peer('companion', create=False)
wear(b, TOP, held=companion_at)


def glow_client(config, capture, options=''):
    """The test client capturing at PEAK and TROUGH of its glow clock, with
    Option.ini `options` (PQ-339: the glow runs turn the effect off)."""
    lines = []
    account, password = accounts['archer']
    pathlib.Path(config, 'n3e').mkdir(exist_ok=True)
    pathlib.Path(config, 'n3e', 'Option.ini').write_text(options)
    proc = subprocess.Popen(
        ['build/client/n3e-test-client', str(package), '--connect', 'localhost:' + str(state['port']), '--ca',
         'deploy/local/ca.pem', '--auto-login', '--fixed-window', '1280x1024', '--world-smoke', '14',
         '--capture', str(capture)],
        env={**env, 'N3E_TEST_ACCOUNT': account, 'N3E_TEST_PASSWORD': password, 'N3E_TEST_EQUIPMENT_GLOW': '1',
             'N3E_TEST_EQUIPMENT_GLOW_CAPTURES': f'{PEAK},{TROUGH}', 'N3E_TEST_APPEARANCE_EFFECTS': '1',
             'N3E_TEST_APPEARANCE_TAIL_THIN': '1', 'XDG_CONFIG_HOME': config},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    reader = threading.Thread(target=lambda: lines.extend(proc.stdout), daemon=True)
    reader.start()
    while proc.poll() is None:
        b.pump(.1)
    reader.join(10)
    text = ''.join(lines)
    capture.with_suffix('.log').write_text(text)
    exited(proc.returncode, text)
    made = re.findall(r'^EQUIPMENT_GLOW_CAPTURE at=([0-9.]+) drawn=[0-9.e+-]+ path=(.+)$', text, re.M)
    assert [float(t) for t, _ in made] == [PEAK, TROUGH], (made, text[-1500:])
    VIEW.check(capture.name, text)
    return text, [pathlib.Path(p) for _, p in made]


def pulse(t):
    c = math.fmod(t, 5.5)
    return c if c <= 1 else 1 if c <= 3 else 1 - (c - 3) * .5 if c <= 5 else 0


def brighter(a, b, box, levels=40):
    """Pixels of `box` at least `levels` brighter (channel sum / 3) in capture `a` than in `b`."""
    width, height, pa = npc_looks_live.read_ppm(a)
    _, _, pb = npc_looks_live.read_ppm(b)
    x0, y0, x1, y1 = box
    return sum(sum(pa[(y * width + x) * 3:(y * width + x) * 3 + 3]) - sum(pb[(y * width + x) * 3:(y * width + x) * 3 + 3])
               >= 3 * levels for y in range(max(0, y0), min(height, y1 + 1)) for x in range(max(0, x0), min(width, x1 + 1)))


GLOW_OUT = root / 'build/pq337/moradon'
GLOW_OUT.mkdir(parents=True, exist_ok=True)
EFFECT_OUT = root / 'build/pq339/moradon'
EFFECT_OUT.mkdir(parents=True, exist_ok=True)
# Pixels of a bow box the main bundle must give at least GREEN more green than
# EffectVisible=0, at least half that in red and at most half in blue (the
# poison frames are green-yellow, added), over both clock seconds; the reverse
# comparison is the two clients' breathing alone (none since PQ-400, which
# found it was the wearers' base clips, timed from the host's uptime; the
# numbers below are from before). PQ-339 asked for 60 levels
# with a third in blue at each second (55 to 178 pixels, the reverse 0 to 4);
# since PQ-341 the tail's violet haze lies over the bow too and lifts the blue
# of many of them (with 60 levels the reverse reached 23 over both seconds
# against 82; with 80 levels, 24 to 91 at a second and 72 to 131 over both,
# the reverse 2 to 7 and 8 to 12, in PQ-341's development runs).
EFFECT_PIXELS, GREEN = 40, 80
# PQ-341: pixels of a bow box the tail must give at least BLUE more blue than
# EffectVisible=0 with at most a third of that in green, at each clock second
# (its violet particles and mesh, added; 1,474 to 3,826 in its first run, the
# reverse 1 to 5).
TAIL_PIXELS, BLUE = 300, 40
NO_EFFECT = '[WeaponEffect]\nEffectVisible=0\n'
NO_GLOW = '[Addition2233]\nEquipmentGlow=0\n'
with tempfile.TemporaryDirectory(dir=root / 'build') as config:
    text, lit = glow_client(config, GLOW_OUT / 'azagai-glow-on.ppm', NO_EFFECT)
    quiet, unlit = glow_client(config, GLOW_OUT / 'azagai-glow-off.ppm', NO_EFFECT + NO_GLOW)
    # PQ-339: the effect alone, the glow off in both.
    shown_text, shown = glow_client(config, EFFECT_OUT / 'azagai-effect-on.ppm', NO_GLOW)
    hidden_text, hidden = glow_client(config, EFFECT_OUT / 'azagai-effect-off.ppm', NO_GLOW + NO_EFFECT)
assert 'PLUG_GLOW ' not in quiet and 'off by Option.ini' in quiet, quiet[-1500:]
assert 'APPEARANCE_EFFECT' not in text + quiet + hidden_text, 'an effect drawn with EffectVisible=0'
assert 'PLUG_GLOW ' not in shown_text + hidden_text, 'a glow drawn with EquipmentGlow=0'
other = b.id
low, high = KEYS[LOW], KEYS[TOP]
start = r'^PLUG_GLOW entity=(\d+) self=(\d) key=(\d+) entry=(\d) wave=(\w+) modulate=(\d) color=1,1,1 vertices=(\d+)$'
glowing = {int(e): (int(s), int(k), w, int(m)) for e, s, k, _, w, m, _ in re.findall(start, text, re.M)}
mine = [e for e, (s, *_) in glowing.items() if s == 1]
assert len(mine) == 1 and glowing.get(other) == (0, high, 'steady', 2) and glowing[mine[0]] == (1, low, 'pulse', 1), \
    glowing
mine = mine[0]
samples = [(int(e), int(k), float(t), float(i)) for e, k, t, i in re.findall(
    r'^PLUG_GLOW_SAMPLE entity=(\d+) key=(\d+) t=([0-9.e+-]+) intensity=([0-9.e+-]+)$', text, re.M)]
ours = [(t, i) for e, k, t, i in samples if e == mine]
theirs = [i for e, k, t, i in samples if e == other]
assert len(ours) >= 8 and all(abs(i - pulse(t)) < 1e-3 for t, i in ours), ours
assert len(theirs) >= 8 and all(i == 1 for i in theirs), theirs
boxes = {}
for at, e, k, box in re.findall(r'^EQUIPMENT_GLOW_BOX at=([0-9.]+) entity=(\d+) self=\d key=(\d+) box=(\S+)$', text, re.M):
    boxes[float(at), int(e)] = tuple(int(v) for v in box.split(','))
assert {e for _, e in boxes} == {mine, other}, boxes
area = lambda box: (box[2] - box[0] + 1) * (box[3] - box[1] + 1)  # noqa: E731
gain = {(t, e): brighter(lit[n], unlit[n], boxes[t, e]) for n, t in enumerate((PEAK, TROUGH)) for e in (mine, other)}
share = {k: round(v / area(boxes[k]), 4) for k, v in gain.items()}
# At the peak both bows are lit up; at the trough the +1's pulse is 0 and only
# the +30's steady light (at 2x) is left. Until PQ-400 two clients' bodies and
# bows breathed out of step (each wearer's layered base clip ran from the host's
# uptime, not from first sight), so without any glow some pixels still differed
# by 40 levels (0.6 to 1.8 % of a box with the glow left out of the draw, up to
# 4.1 % at the +1's trough, against 11 to 12 % lit); now two clients draw the
# same frame (checked below): a glow must lift LIT of its box's pixels, and the
# +1 at its trough must not.
assert share[PEAK, mine] >= LIT and share[PEAK, other] >= LIT and share[TROUGH, other] >= LIT, share
assert share[TROUGH, mine] < LIT, share
# PQ-400: two clients with the same options (the effect and the glow off:
# glow-off and effect-off) capture the same frame at each clock second: in each
# bow box at most SAME of the pixels differ by 40 levels in any channel (0 in
# PQ-400's runs; up to 11 % before, when the wearers' base clips ran from the
# host's uptime).
SAME = .005


def differing(a, b, box, levels=40):
    width, height, pa = npc_looks_live.read_ppm(a)
    _, _, pb = npc_looks_live.read_ppm(b)
    x0, y0, x1, y1 = box
    return sum(max(abs(pa[i + c] - pb[i + c]) for c in range(3)) >= levels
               for y in range(max(0, y0), min(height, y1 + 1)) for x in range(max(0, x0), min(width, x1 + 1))
               for i in ((y * width + x) * 3,))


for ppm in (*lit, *unlit):
    w, h, pixels = npc_looks_live.read_ppm(ppm)
    png(ppm.with_suffix('.png'), w, h, [pixels[y * w * 3:(y + 1) * w * 3] for y in range(h)])
digests = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (*lit, *unlit)}
print(f"PASS Moradon client draws the Azagai reverse grades' glow on the skeletal plug (the weapon effect off in "
      f"both clients): the local reverse +1 pulses at 1x "
      f"({len(ours)} samples on 0056ea30's pulse), the other's reverse +30 stays lit at 2x ({len(theirs)} samples "
      f"at 1); pixels at least 40 levels brighter than EquipmentGlow=0 in the bow boxes: at {PEAK} s +1 "
      f"{gain[PEAK, mine]} ({share[PEAK, mine]:.1%}), +30 {gain[PEAK, other]} ({share[PEAK, other]:.1%}); at "
      f"{TROUGH} s +1 {gain[TROUGH, mine]} ({share[TROUGH, mine]:.1%}), +30 {gain[TROUGH, other]} "
      f"({share[TROUGH, other]:.1%}); one view in every capture run ({VIEW.summary()}); captures {digests}",
      flush=True)

# PQ-339: the weapon effect on both reverse grades' keys, against EffectVisible=0.
line = r'^APPEARANCE_EFFECT entity=(\d+) self=(\d) key=(\d+) copies=3 vertices=222 tails=2 trace=ffff00ff '
started = {int(e): (int(s), int(k)) for e, s, k in re.findall(line, shown_text, re.M)}
# The local player's entity is new on every login; the other's is the same.
assert sorted(started.values()) == [(0, high), (1, low)] and started.get(other) == (0, high), (
    started, re.findall(r'^APPEARANCE_EFFECT.*$', shown_text, re.M))


def greener(a, b, box):
    """Pixels of `box` at least GREEN greener in capture `a` than in `b`,
    gaining at least half of that in red and at most half in blue."""
    width, height, pa = npc_looks_live.read_ppm(a)
    _, _, pb = npc_looks_live.read_ppm(b)
    x0, y0, x1, y1 = box
    n = 0
    for y in range(max(0, y0), min(height, y1 + 1)):
        for x in range(max(0, x0), min(width, x1 + 1)):
            i = (y * width + x) * 3
            r, g, bl = pa[i] - pb[i], pa[i + 1] - pb[i + 1], pa[i + 2] - pb[i + 2]
            n += g >= GREEN and r >= g / 2 and bl <= g / 2
    return n


def bluer(a, b, box):
    """PQ-341: pixels of `box` at least BLUE bluer in capture `a` than in
    `b`, gaining at most a third of that in green: the tail's violet particles
    and mesh, added (blend 5/2), which the main bundle's green-yellow frames do
    not give."""
    width, height, pa = npc_looks_live.read_ppm(a)
    _, _, pb = npc_looks_live.read_ppm(b)
    x0, y0, x1, y1 = box
    n = 0
    for y in range(max(0, y0), min(height, y1 + 1)):
        for x in range(max(0, x0), min(width, x1 + 1)):
            i = (y * width + x) * 3
            g, bl = pa[i + 1] - pb[i + 1], pa[i + 2] - pb[i + 2]
            n += bl >= BLUE and g <= bl / 3
    return n


same = {(t, e): differing(unlit[k], hidden[k], boxes[t, e]) for k, t in enumerate((PEAK, TROUGH)) for e in (mine, other)}
assert all(n <= SAME * area(boxes[k]) for k, n in same.items()), same
effect = {(t, e): (greener(shown[k], hidden[k], boxes[t, e]), greener(hidden[k], shown[k], boxes[t, e]))
          for k, t in enumerate((PEAK, TROUGH)) for e in (mine, other)}
tail = {(t, e): (bluer(shown[k], hidden[k], boxes[t, e]), bluer(hidden[k], shown[k], boxes[t, e]))
        for k, t in enumerate((PEAK, TROUGH)) for e in (mine, other)}
# On both bows, over both clock seconds: the main bundle's green-yellow, not
# the breathing.
both = {e: tuple(sum(effect[t, e][k] for t in (PEAK, TROUGH)) for k in (0, 1)) for e in (mine, other)}
assert all(n >= EFFECT_PIXELS and n >= 4 * back for n, back in both.values()), (both, effect)
# PQ-341: and the tail's violet.
assert all(n >= TAIL_PIXELS and n >= 4 * back for n, back in tail.values()), tail
for ppm in (*shown, *hidden):
    w, h, pixels = npc_looks_live.read_ppm(ppm)
    png(ppm.with_suffix('.png'), w, h, [pixels[y * w * 3:(y + 1) * w * 3] for y in range(h)])
digests = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (*shown, *hidden)}
print(f"PASS Moradon skeletal plug weapon effect graphical: the client draws 32120 on the Azagai's FX mesh for the "
      f"local reverse +1 and the other's reverse +30 (APPEARANCE_EFFECT: three copies of 222 vertices, two tails, "
      f"trail ffff00ff); "
      f"pixels at least {GREEN} levels greener (half that in red, at most half in blue) than EffectVisible=0 in "
      f"the bow boxes (and the reverse): at {PEAK} s +1 {effect[PEAK, mine]}, +30 {effect[PEAK, other]}; at "
      f"{TROUGH} s +1 {effect[TROUGH, mine]}, +30 {effect[TROUGH, other]}; PQ-341: and its tail 32121 (a 20 s clip "
      f"of two 10 s links: turning meshes and falling particles), pixels at least {BLUE} levels bluer (little "
      f"green): at {PEAK} s +1 {tail[PEAK, mine]}, +30 {tail[PEAK, other]}; at {TROUGH} s +1 {tail[TROUGH, mine]}, "
      f"+30 {tail[TROUGH, other]}; PQ-400: two clients with the effect and the glow off differ in "
      f"{[same[k] for k in sorted(same)]} pixels of the bow boxes by 40 levels (at most {SAME:.1%}); captures {digests}",
      flush=True)

def thin_lines(text_):
    """PQ-342: the client's rule state on each tail link (APPEARANCE_TAIL_THIN)."""
    return [dict(entity=int(m[1]), self=m[2] == '1', rule=int(m[3]), count=int(m[4]), near=float(m[5]),
                 far=float(m[6]), distance=float(m[7]), target=int(m[8]), drawn=int(m[9]), carried=int(m[10]),
                 copy=int(m[11]))
            for m in re.finditer(
        r'^APPEARANCE_TAIL_THIN entity=(\d+) self=(\d) rule=(\d+) texture=\d+ count=(\d+) near=(\S+) far=(\S+) '
        r'link=\S+ age=\S+ distance=(\S+) target=(-?\d+) drawn=(\d+) carried=(\d+) copy=(\d+)$', text_, re.M)]


def thin_target(l):
    d = l['distance']
    return l['count'] if d < l['near'] else int((l['far'] - d) / l['far'] * l['count'])


# PQ-342, the near side: in the effect captures both players' tails lie within
# 20 m of the camera (the sparks' near, and the puffs' 40 m), so every rule
# keeps its pool, which the captures above draw.
near_lines = thin_lines(shown_text)
assert {(l['rule'], l['count'], l['near'], l['far']) for l in near_lines} == {
    (k, *r) for k, r in enumerate(RULES)}, near_lines[:8]
# (The local player's entity is new on every login: it is the self one.)
close = {'+1': [l for l in near_lines if l['self']], '+30': [l for l in near_lines if l['entity'] == other]}
assert all(len(v) >= 40 and max(l['distance'] for l in v) < 20 and all(l['target'] == l['count'] for l in v)
           for v in close.values()), {e: [(l['distance'], l['target']) for l in v][:6] for e, v in close.items()}
assert all(max(l['drawn'] for l in v if l['rule'] == k) > 0 for v in close.values() for k in range(4))
reach = {e: (round(min(l['distance'] for l in v), 1), round(max(l['distance'] for l in v), 1))
         for e, v in close.items()}
# PQ-350: the first account changes to the normal +10 (attribute 4): its bow
# draws no glow (no PLUG_GLOW for its key; its box, where the reverse +1 stood,
# no brighter than with EquipmentGlow=0 at either second) while the other's
# reverse +30 still glows; the inventory names it (its effect: the PQ-342 run).
mine_before = mine
b.logout()
a = peer('archer', create=False)
wear(a, NORMAL, held=low_at)
a.logout()
inventory_view('gear', NORMAL)
b = peer('companion', create=False)
other = b.id  # a new entity after its login
with tempfile.TemporaryDirectory(dir=root / 'build') as config:
    plain_text, plain = glow_client(config, GLOW_OUT / 'azagai-normal10.ppm', NO_EFFECT)
plain_glowing = {int(e): (int(s), int(k), w, int(m)) for e, s, k, _, w, m, _ in re.findall(start, plain_text, re.M)}
assert list(plain_glowing.values()) == [(0, high, 'steady', 2)] and other in plain_glowing, plain_glowing
assert not re.search(r'^PLUG_GLOW entity=\d+ self=1 ', plain_text, re.M) and not re.search(
    r'^EQUIPMENT_GLOW_BOX at=\S+ entity=\d+ self=1 ', plain_text, re.M), plain_text[-1500:]
plain_share = {t: round(brighter(plain[n], unlit[n], boxes[t, mine_before]) / area(boxes[t, mine_before]), 4)
               for n, t in enumerate((PEAK, TROUGH))}
assert all(v < LIT for v in plain_share.values()), plain_share
print(f"PASS Moradon client draws no glow on the normal +10 Azagai (1110432510, attribute 4: no PLUG_GLOW for key "
      f"{KEYS[NORMAL]}) while the other's reverse +30 still glows at 2x; in the local bow's box "
      f"{plain_share} of the pixels are 40 levels brighter than with EquipmentGlow=0 (a glow lifts {LIT:.0%})",
      flush=True)
# The far side: the other walks out to FAR_WALK m from the spawn (the camera
# then 20-40 m from its tail), where 2233 keeps the puffs' pool and cuts the
# sparks to trunc(11 x (50 - d) / 50), and a client with the effect on reads
# the rule state again.
FAR_WALK = 25


def walk_out(p, radius, seconds=90):
    """Walk `p` from the spawn until it is `radius` m away, ahead of the
    camera's opening view first, turning to the next direction when blocked
    for 2 s. Returns where it stopped, from the spawn, or None."""
    end = time.monotonic() + seconds
    for ux, uz in ((0, -1), (.7, -.7), (-.7, -.7), (1, 0), (-1, 0), (.7, .7), (-.7, .7), (0, 1)):
        last, still = None, time.monotonic()
        while time.monotonic() < end:
            p.pump(.05)
            me = p.entities[p.id]
            if first(me, 6) < p.seq:
                continue
            x, z = first(me, 3), first(me, 5)
            if math.hypot(x - sx, z - sz) >= radius:
                p.move(0, 0)
                p.pump(.2)
                return round(x - sx, 1), round(z - sz, 1)
            if last is None or math.hypot(x - last[0], z - last[1]) > .05:
                last, still = (x, z), time.monotonic()
            elif time.monotonic() - still > 2:
                break
            p.move(ux, uz, mode=0)
    p.move(0, 0)
    return None


far_at = walk_out(b, FAR_WALK)
assert far_at, f'no walkable way {FAR_WALK} m out from the spawn'
b.pump(1)
with tempfile.TemporaryDirectory(dir=root / 'build') as config:
    far_text, far_shots = glow_client(config, EFFECT_OUT / 'azagai-effect-far.ppm', NO_GLOW)
# PQ-350: the local normal +10 draws the same weapon effect as the reverse
# grades (Item_Ext_9 row 1510: effect 32120, poison 120, attribute 4).
assert {(int(s_), int(k)) for _, s_, k in re.findall(line, far_text, re.M)} == {(1, KEYS[NORMAL]), (0, high)}, \
    re.findall(r'^APPEARANCE_EFFECT.*$', far_text, re.M)
far_lines = [l for l in thin_lines(far_text) if l['entity'] == other]
ours_far = [l for l in thin_lines(far_text) if l['self']]
every = near_lines + thin_lines(far_text)
assert all(l['target'] == thin_target(l) for l in every if abs(l['distance'] - l['near']) > 1e-3), [
    l for l in every if l['target'] != thin_target(l)]
cut = [l for l in far_lines if 20 < l['distance'] < 40]
assert len(cut) >= 40, ([(l['distance'], l['target']) for l in far_lines][:10], far_at)
assert all(l['target'] == 20 for l in cut if l['rule'] < 2), cut[:4]
# A tail copy's links share one live list: what the copy draws (its links'
# drawn ones summed, copy) stays within the target and one more, and so does a
# link's drawn ones with the earlier link's taken live ones it counted.
top = {k: max(c['target'] for c in cut if c['rule'] == k) for k in (2, 3)}
assert all(0 < l['target'] < 11 and l['drawn'] + l['carried'] <= top[l['rule']] + 1
           and l['copy'] <= top[l['rule']] + 1 for l in cut if l['rule'] >= 2), [
    (l['distance'], l['target'], l['drawn'], l['carried'], l['copy']) for l in cut if l['rule'] >= 2]
handover = [l for l in cut if l['rule'] >= 2 and l['carried']]
assert handover, 'no sample across a link handover (one every 10 s)'
assert ours_far and all(l['target'] == l['count'] for l in ours_far), ours_far[:4]
sparks = {k: (sorted({l['target'] for l in cut if l['rule'] == k}),
              max(l['copy'] for l in cut if l['rule'] == k)) for k in (2, 3)}
near_sparks = {k: max(l['drawn'] for l in close['+30'] if l['rule'] == k) for k in (2, 3)}
print(f"PASS Moradon client thins the Azagai tail's particles by the camera's distance (PQ-342, 2233 00592900): "
      f"with both tails within 20 m ({reach} m) every rule keeps its pool (the captures above draw it; the other's "
      f"sparks drew up to {near_sparks}); with the other walked out to {far_at} m from the spawn "
      f"({round(min(l['distance'] for l in cut), 1)}-{round(max(l['distance'] for l in cut), 1)} m from the camera) "
      f"the puffs keep their pool of 20 and the sparks' targets and most drawn per tail copy (both links) are "
      f"{sparks}, trunc(11 x (50 - d) / 50) and at most one more ({len(handover)} samples across a link handover); "
      f"the local player's tail keeps every pool; the local normal +10 draws the same effect 32120 (APPEARANCE_EFFECT "
      f"on key {KEYS[NORMAL]}: three copies, two tails, trail ffff00ff)",
      flush=True)
b.logout()
