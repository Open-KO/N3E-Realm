"""PQ-317: skeletal weapon plugs (N3AT plug entries), live.

The rule is the 2233 client's CN3ChrTypePlug (a 2233/2145 addition; KO 1298 has
none): a hand item can be a whole animated character on the hand joint, placed
at plug matrix x joint x parent (00434980), playing its own clock (00433b30 with
FLT_MIN, 0042e070) with the clip 0042df00 maps the parent's clip to (00432760;
applied to every wearer, D-188). Evidence:
docs/implementation/evidence/pq-317-skeletal-weapon-plugs-2233.md.

The package is the PQ-328 fixture (tests/attached_characters_live.py: the
PQ-272 package with the wing and fairy slots) with one more item, an original
synthetic bow (tools/assetc/skeletal_plug_fixture.py) that fits only the left
hand (slot 1), its appearance key 4 with an empty N3D2 mesh, and a plug entry
on the player's joint 1: a quarter-turn 0.8 placement and a clip map that sways
the bow's upper limb (slot 0, looped) for every pose state but attack and ready.

Both readers must accept the package and refuse malformed plug entries, and the
client must refuse an empty appearance mesh for a key no plug entry names.
Against a native server on a disposable Postgres and Redis the server must
refuse the bow in the right hand and in the wing slot, and two accounts equip it
in the left hand over the wire; it stays equipped across sessions. With
N3E_GRAPHICAL=1 the real test client logs in as the first account while the
second stands 3 m ahead, and must:

- draw the bow on both players (an ATTACHMENT line for each, lit 0, modulate 1,
  no emissive), never advancing a pulse clock for it;
- place it from the drawn vertices: the centre of the vertices drawn for each
  sample is the wearer's frame x the joint's matrix (both printed) x the
  package's placement applied to the centre of the bow's skinned model, which
  is the fixture's own centre for the sampled clip time (fails without the
  placement, the joint, or the clip);
- advance its clip: the sampled slot-0 times take at least four values, and
  the skinned centre swings with them (fails with the clip frozen);
- keep slot 0 playing while the other player walks aside (2233 keeps the
  playing clip for the same index; PQ-328's wing changes clip there), play
  slot 2 once while the other casts the fixture's skill (the map's skill row),
  holding its end, and slot 0 again after the cast;
- capture at 6.25 s and 6.75 s of the local wearer's drawn time, the sway's two
  extremes: inside the screen box of each player's bow (the union of both
  captures' boxes) at least SWING of the pixels differ between the captures
  (fails without the plug drawn or with its clip frozen);
- PQ-337: the bow's key also carries an equipment glow (N3E3, a white pulse
  at 2x), which 2233 hands to the plug's inner character (0056ea30 ->
  0042de90 -> 00430f40): the client must draw it on the whole bow of both
  players (PLUG_GLOW), its sampled intensities must follow 0056ea30's pulse on
  each wearer's glow clock, and at PEAK of that clock the bow boxes must hold
  pixels brighter than a second client's with [Addition2233] EquipmentGlow=0,
  and gain LIFTED pixels at or above WHITE, which only the 2x gives the grey
  128 bow (fails without the glow on the plug or without its modulate).
- PQ-339: the bow's key also carries a weapon effect (N3E2 on the same file:
  a magenta three-frame glow, three copies of a cross on the wearer's joint 1
  beside the body, away from the bow, and no tail), as 2233 draws a
  CN3ChrTypePlug's FX mesh effect rigid on the hand joint (CN3Chr::Render
  00435440 -> 00433af0 -> 004304c0): the client must draw it on both players
  (APPEARANCE_EFFECT for itself and the other, three copies, no tails) and the
  capture at PEAK must show two magenta glows, which a client with
  [WeaponEffect] EffectVisible=0 draws none of (fails without the effect on a
  plug key or with the client unable to read an effect with no tail clip).
- PQ-341: the effect also carries a tail, the original synthetic 2233 tail
  (tools/assetc/fx_tail_2233_fixture.py: two turning mesh parts and two
  particle parts, all green) cooked by ko_fx_tail_2233 into a 20 s clip of
  two 10 s links on a tail box beside the cross, as 2233's RenderFX
  (004304c0) draws the tail copies at points of the FX mesh box: the client
  must read the clip (APPEARANCE_EFFECT with two tails) and the capture at
  PEAK must hold two green patches (pixels at least GREEN greener than
  EffectVisible=0, little red or blue), one per player, and the reverse
  comparison none (fails without the tail drawn or with the client refusing a
  20 s clip).
- PQ-342: the tail's particle parts carry 2233's camera-distance rule
  (00592900) as N3E4 rules: the green kind-2 part 40 and 70 m, the lime kind-1
  part SPLIT and 12 m, and a third, red part (0.6 m along +x) SPLIT and 8.4 m.
  The camera is about 7.3 m from the local player's tail and 9.8 m from the
  other's at AHEAD, on either side of SPLIT. The client's rule state
  (APPEARANCE_TAIL_THIN) must give 2233's target for every printed distance,
  the local player's three pools and, for the other standing at AHEAD, the
  green pool, a lime target of 1 or 2 with at most 3 drawn, and a negative red
  target with none drawn; the capture at PEAK must hold a red patch beside the
  local player's glow and none beside the other's (fails with the client
  drawing every candidate, with near ignored, or with no rules cooked).
- PQ-359: the local player also wears the blade, whose quad's normal is the
  bow's (+z, which every turn on the bow's path, all about z, keeps), and a
  client with [Addition2233] EquipmentGlow=0 and [WeaponEffect] EffectVisible=0
  captures at LIGHT_AT s: the bow's light factor (its drawn grey over its
  texture's 128) must equal the blade's (over its white texel) within
  LIGHT_TOLERANCE, as 1298's 004196a0 lights a character's parts and plugs
  alike (fails with the plug drawn in another light, as before PQ-359 the
  looks models' 0.15 + light x max(N.n(0.3, 0.4, 1), 0)).
"""
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tests") not in sys.path:
    sys.path.append(str(ROOT / "tests"))
from isolation import once_per_run  # noqa: E402
import appearance_effects_live as effects_live  # noqa: E402
import attached_characters_live as attached_live  # noqa: E402
import equipment_glow_live as glow_live  # noqa: E402
import npc_looks_live  # noqa: E402

OUT = ROOT / "build/pq317/synthetic"
BOW = "demo:item/bow"
KEY, ENTRY = 4, 2  # the bow's appearance key and N3AT entry
A, B = 6.25, 6.75  # the local wearer's drawn seconds: the sway at +0.6 and -0.6 rad
AHEAD = effects_live.AHEAD
ASIDE = (AHEAD[0] + 3.0, AHEAD[1])
SWING = 0.10  # share of a bow box's pixels that differ between the two captures
# PQ-337: the bow's key glows (N3E3: a white pulse at 2x). PEAK is a second of
# the local player's glow clock where 0056ea30's pulse holds 1 (1 to 3 s).
PEAK = 2.0
WHITE = 230  # every channel at or above: the grey 128 bow lifted to 255 by the emissive at 2x (128 at 1x)
LIFTED = 30  # pixels each bow box must gain at or above WHITE over EquipmentGlow=0
# PQ-339: the bow key's weapon effect, beside the body on the side away from
# the bow (which hangs at x -0.16 of joint 1), so it leaves the bow boxes alone.
EFFECT_X = 0.8
POISON = 0xffff00ff  # the trail colour it carries (not drawn)
# PQ-341: the tail's box, beside the cross on the side away from the body, and
# the name of its clip; a tail pixel gains GREEN green over EffectVisible=0,
# red and blue within TINT; each player's green patch has PATCH pixels.
TAIL_BOX = [[EFFECT_X + .3, .3, 0], [EFFECT_X + .7, .3, 0], [EFFECT_X + .3, .9, 0], [EFFECT_X + .3, .3, .1]]
TAIL_CLIP = "tail-2233"
GREEN, TINT, PATCH, NEAR = 60, 30, 20, 40
# PQ-342: the camera is about 7.3-7.5 m from the local player's tail and
# 9.7-9.9 m from the other's at AHEAD (the development runs' distances), so
# with near 8 m the local player's parts draw their whole pool; the kind-1
# (lime) part's far 12 m gives the other a target of trunc(12 x (12 - d) / 12)
# = 1 or 2, and the red part's far 8.4 m a negative one: none taken. (Within
# far x (1 + 1/12) = 9.1 m of the camera the target truncates to 0, which
# still takes a candidate when none is alive and draws it once the target
# turns negative, as 2233's 00592740 does.)
SPLIT = 8.0
LIME_RULE, RED_RULE = (SPLIT, 12.0), (SPLIT, 8.4)
STANDING = 6.0
# PQ-359: the blade (key 1) beside the bow; the light capture's second of the
# local wearer's attachment clock; the largest factor difference allowed (the
# bow's 128 and the blade's 255 texels round differently, about 0.004).
BLADE, BLADE_KEY = "demo:item/blade", 1
LIGHT_AT = 3.0
LIGHT_TOLERANCE = 0.02


def fixture():
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    import skeletal_plug_fixture
    return skeletal_plug_fixture


def detail(empty_wing=False):
    """The PQ-328 fixture's render detail and, for the bow's key 4, an empty
    mesh (a plug key draws no rigid mesh). `empty_wing` also empties the wing
    key's mesh, which the client must refuse (no plug entry names key 2).
    PQ-359: the blade quad's normal is the bow's, +z."""
    import render_detail

    def body(slot):
        return ([([x, 0, z], [0, 1, 0], [x, z], [0] * 4, [1, 0, 0, 0], slot) for x, z in [(0, 0), (1, 0), (0, 1)]],
                [0, 1, 2])

    def quad(slot):
        corners = [(.3, .2), (.9, .2), (.9, .8), (.3, .8)]
        vertices = [([x, y, 0], [0, 0, 1], [x, y], [0] * 4, [1, 0, 0, 0], slot) for x, y in corners]
        return vertices, [0, 1, 2, 0, 2, 3, 0, 2, 1, 0, 3, 2]

    def speck(slot):
        return ([([x, .01, z], [0, 1, 0], [0, 0], [0] * 4, [1, 0, 0, 0], slot) for x, z in [(0, 0), (.01, 0), (0, .01)]],
                [0, 1, 2])
    empty = ([], [])
    white, grey = [(16, 16, bytes([255]) * 1024)], [(16, 16, bytes([90, 90, 90, 255]) * 256)]
    return render_detail.serialize(
        view=[1.134464, .5, 256], thresholds=[[6, 18, 32, 128]] * 4, workload=[30, 60, 100], world_count=1,
        textures=[white, white, grey], radius=1, levels=[body(1)] * 4,
        appearances=[([1], [quad(2)] * 4), ([], [empty if empty_wing else speck(1)] * 4), ([], [speck(1)] * 4),
                     ([], [empty] * 4)])


def with_textures(n3ef, colours):
    """`n3ef` with a 4 x 4 texture of each colour appended to its textures (the
    existing ones keep their ids); returns (bytes, the new ids)."""
    count = struct.unpack_from("<I", n3ef, 4)[0]
    at = 8
    for _ in range(count):
        w, h = struct.unpack_from("<II", n3ef, at)
        at += 8 + w * h * 4
    new = b"".join(struct.pack("<II", 4, 4) + bytes([*c, 255]) * 16 for c in colours)
    return n3ef[:4] + struct.pack("<I", count + len(colours)) + n3ef[8:at] + new + n3ef[at:], \
        list(range(count, count + len(colours)))


def effect_entry(frames, tails=2):
    """PQ-339: the bow key's weapon effect, on the wearer's joint 1; PQ-341:
    with two links of the synthetic 2233 tail (`tails` 0: none)."""
    cross = effects_live.cross
    return effects_live.entry(
        key=KEY, joint=1, frames=frames, tails=tails, tail_clip=TAIL_CLIP if tails else "", trace_color=POISON,
        copies=[dict(jitter=0, frame_offset=0, vertices=cross(EFFECT_X, .3, .9)),
                dict(jitter=1, frame_offset=1, vertices=cross(EFFECT_X + .02, .3, .9)),
                dict(jitter=-1, frame_offset=2, vertices=cross(EFFECT_X - .02, .3, .9))],
        tail_box=TAIL_BOX)


def with_tail(n3ef):
    """PQ-341: `n3ef` with the synthetic 2233 tail cooked by ko_fx_tail_2233
    (its target scale from the tail box's y and z extents, x 0.7, as InitFX
    00437510 takes it): the textures it names appended, its clip added first."""
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    import fx_tail_2233_fixture as fx
    import ko_fx_tail_2233
    import ko_tiles
    count = struct.unpack_from("<I", n3ef, 4)[0]
    at = 8
    for _ in range(count):
        w, h = struct.unpack_from("<II", n3ef, at)
        at += 8 + w * h * 4
    added, ids = [], {}

    def texture(name, source):
        if name not in ids:
            w, h, pixels = ko_tiles.mip_chains(source.get(name), dxt5=True)[0][0]
            ids[name] = count + len(added)
            added.append(struct.pack("<II", w, h) + bytes(pixels))
        return ids[name]
    extent = [TAIL_BOX[k + 1][k] - TAIL_BOX[0][k] for k in range(3)]
    geometry = dict(tail_scale=(extent[1] + extent[2]) * .7)
    tail = fx.files(fx.bundle(fx.parts(lime=LIME_RULE, red=RED_RULE)))
    clip, report = ko_fx_tail_2233.tail_clip(fx.Source(tail), texture,
                                             dict(tail=fx.TAIL, tail_id=1, geometry=geometry), TAIL_CLIP)
    assert (report["link_seconds"], report["frames"]) == (10.0, 600), report
    clips = struct.unpack_from("<I", n3ef, at)[0]
    return (n3ef[:4] + struct.pack("<I", count + len(added)) + n3ef[8:at] + b"".join(added)
            + struct.pack("<I", clips + 1) + clip + n3ef[at + 4:]), \
        [dict(rule, clip=TAIL_CLIP) for rule in report["thinning"]]


def bow_entry(root):
    bow = fixture()
    rows = bow.CLIP_MAP + [dict(kind="combat", id=i, slot=1, once=True) for i in range(3)] \
        + [dict(kind="skill", id=0, slot=2, once=True)]
    return dict(item=BOW, slot=1, joint=1, scale=1.0, group=2,
                plug=dict(placement=list(bow.PLACEMENT), clips=rows), clips=bow.write(root))


def source(root):
    """The PQ-328 fixture source at `root` plus the bow: its item, key 4 and
    plug entry."""
    m = attached_live.source(root)
    m["equipment"]["items"].append(dict(id=BOW, slots=[1], blocks=[], race=0, title=0, attributes=[0] * 5,
                                        swappable=False))
    m["inventory"]["items"].append(dict(id=BOW, label="Bow", stack_limit=1, durability=0, starting=1))
    # Offered by no shop, weightless, no wear and no stats: presentation only.
    m["commerce"]["items"].append(dict(id=BOW, weight=0, price=1, sell_divisor=10000))
    m["wear"]["items"].append(dict(id=BOW, attack_slots=[], defense_slots=[]))
    m["stats"]["items"].append(dict(id=BOW, category="demo:weapon/none", attack=0, defense=0, health=0,
                                    resource=0, accuracy=0, evasion=0, attributes=[0] * 5))
    m["appearance"].append(dict(item=BOW, slot=1))
    m["attachments"]["entries"].append(bow_entry(root))
    (root / "detail.bin").write_bytes(detail())
    # PQ-337: the bow's key carries an equipment glow (a white pulse at 2x),
    # which 2233 hands to the plug's inner character (0042de90, 00430f40).
    # PQ-339: and a weapon effect (2233 004304c0 on the FX mesh); PQ-341:
    # with the synthetic 2233 tail.
    import appearance_effects
    effects, frames = with_textures((root / "effects.bin").read_bytes(), effects_live.MAGENTA)
    # PQ-342: with its particle parts' camera-distance rules (N3E4).
    effects, rules = with_tail(effects)
    (root / "effects.bin").write_bytes(appearance_effects.n3e4(effects, [effect_entry(frames)],
                                                               [glow_live.glow(key=KEY)], rules, len(m["appearance"])))
    (root / "package.json").write_text(json.dumps(m))
    return m


@once_per_run
def prepare():
    """Cook the PQ-328 package with the bow; returns its directory."""
    from npc_scale_live import prepare as base
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    import main

    root, out = OUT / "source", OUT / "package"
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(base().parent / "source", root)
    source(root)
    main.cook(root, out)
    return out.resolve()


HEADER, ENTRY_BYTES = attached_live.HEADER, attached_live.ENTRY
PLUG_AT = HEADER + 2 * ENTRY_BYTES  # the bow's entry
PLACEMENT_AT = PLUG_AT + ENTRY_BYTES
ROWS_AT = PLACEMENT_AT + 48


def check_readers(package):
    """Both readers accept the package; each refuses the malformed plug entries
    it can see (the client also checks the combat and skill ids against the
    package and the empty meshes against the plug keys). Returns the number of
    refused packages."""
    npc_looks_live.check_readers(package)
    table = (package / "attachments.bin").read_bytes()
    rows = struct.unpack_from("<I", table, ROWS_AT)[0]
    assert len(table) == ROWS_AT + 4 + 16 * rows, (len(table), rows)
    assert struct.unpack_from("<IIfIIfI", table, PLUG_AT) == (KEY, 1, 1.0, 2, 4, 1.0, 0)

    def put(at, value, fmt="<I"):
        return table[:at] + struct.pack(fmt, value) + table[at + struct.calcsize(fmt):]

    def row(i, field, value):
        return put(ROWS_AT + 4 + 16 * i + 4 * field, value)
    both, client_only = "both", "client"
    skill = rows - 1  # the last row is the skill's, the three before it the combat clips'
    cases = [
        ("plug and optional", put(PLUG_AT + 16, 5), "attachment plug flags", both),
        ("plug and lit", put(PLUG_AT + 24, 3), "attachment plug flags", both),
        ("plug at modulate 2", put(PLUG_AT + 20, 2.0, "<f"), "attachment plug flags", both),
        ("singular placement", table[:PLACEMENT_AT] + struct.pack("<12f", *[0.0] * 12) + table[ROWS_AT:],
         "attachment plug placement", both),
        ("placement past 100", put(PLACEMENT_AT + 12, 101.0, "<f"), "attachment plug placement", both),
        ("no clip map rows", table[:ROWS_AT] + struct.pack("<I", 0), "count", both),
        ("unknown kind", row(0, 0, 3), "attachment plug clip map", both),
        ("pose state 10", row(0, 1, 10), "attachment plug clip map", both),
        ("slot 4", row(0, 2, 4), "attachment plug clip map", both),
        ("once 2", row(0, 3, 2), "attachment plug clip map", both),
        ("the same clip twice", row(1, 1, 0), "attachment plug clip map", both),
        ("a row cut short", table[:-4], "", both),
        ("combat clip past the package's 3", row(skill - 1, 1, 3), "attachment plug combat clip", client_only),
        ("unknown skill animation", row(skill, 1, 5), "attachment plug skill animation", client_only),
    ]
    bad = OUT / "hostile"
    refused = 0
    for name, data, reason, who in cases:
        attached_live.repack(package, bad, {"attachments.bin": data})
        p = subprocess.run(["build/client/n3e-asset-check", str(bad)], cwd=ROOT, capture_output=True, text=True)
        assert p.returncode != 0 and reason in p.stdout + p.stderr, (name, p.stdout[-400:], p.stderr[-400:])
        s = subprocess.run(["target/debug/n3e-server", "--check-content"], cwd=ROOT,
                           env={**os.environ, "N3E_PACKAGE": str(bad)}, capture_output=True, text=True)
        assert (s.returncode != 0) == (who == both), (name, s.returncode, s.stdout[-300:], s.stderr[-300:])
        refused += 1
    # An empty mesh is a plug key's only: the wing's key has none, so the
    # client refuses it (the server reads no render detail meshes).
    attached_live.repack(package, bad, {"render-detail.bin": detail(empty_wing=True)})
    p = subprocess.run(["build/client/n3e-asset-check", str(bad)], cwd=ROOT, capture_output=True, text=True)
    assert p.returncode != 0 and "empty appearance" in p.stdout + p.stderr, (p.stdout[-400:], p.stderr[-400:])
    refused += 1
    shutil.rmtree(bad)
    return refused


def frame(sample):
    """The drawn centre the package's rule gives for a PLUG_SAMPLE: the
    wearer's position and heading x the joint's matrix x the placement, applied
    to the centre of the skinned model."""
    p = fixture().PLACEMENT
    m = sample["model"]
    local = [sum(p[r * 4 + c] * m[c] for c in range(3)) + p[r * 4 + 3] for r in range(3)]
    j = sample["joint_matrix"]  # column-major: columns 0-2 then the translation
    v = [sum(j[c * 3 + r] * local[c] for c in range(3)) + j[9 + r] for r in range(3)]
    c, s = math.cos(sample["heading"]), math.sin(sample["heading"])
    w = sample["wearer"]
    return [w[0] + v[0] * c + v[2] * s, w[1] + v[1], w[2] - v[0] * s + v[2] * c]


def plug_samples(text):
    out = []
    for m in re.finditer(r"^PLUG_SAMPLE entity=(\d+) entry=(\d+) slot=(\d) time=(\S+) model=(\S+) bounds=(\S+) placed=(\S+) "
                         r"heading=(\S+) joint_matrix=(\S+) wearer=(\S+)$", text, re.M):
        vec = lambda g: [float(v) for v in g.split(",")]  # noqa: E731
        out.append(dict(entity=int(m[1]), entry=int(m[2]), slot=int(m[3]), time=float(m[4]), model=vec(m[5]),
                        bounds=vec(m[6]), placed=vec(m[7]), heading=float(m[8]), joint_matrix=vec(m[9]),
                        wearer=vec(m[10]), at=m.start()))
    return out


def swing(a, b, box):
    return round(attached_live.share(a, b, box, either=True), 3)


def live(package):
    from isolation import DISPOSABLE_POSTGRES, container_logs, free_ports
    from readiness import wait_postgres
    from world_peer import Peer, blob, fields, first, integer
    import urllib.request

    manifest = json.loads((package / "recipe.json").read_text())["manifest"]
    out = OUT / "live"
    out.mkdir(parents=True, exist_ok=True)
    server_binary = str(Path(os.environ.get("N3E_TEST_SERVER", "target/debug/n3e-server")).resolve())
    name = "n3e-pq317-" + uuid.uuid4().hex[:10]
    passwords = {account: "test-only-" + uuid.uuid4().hex for account in ("archer", "companion")}
    containers, server, log = [], None, None
    bow = fixture()

    def run(*cmd, env=None, stdin=None):
        p = subprocess.run(cmd, env=env, input=stdin, capture_output=True, text=True, timeout=120)
        assert p.returncode == 0, (cmd, p.returncode, p.stdout, p.stderr)
        return p.stdout

    serial = [0]

    def wait(p, tag, predicate=lambda d: True, seconds=8):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            t, d = p.receive()
            assert t != 4, (t, d)
            if t == tag and predicate(d):
                return d
        raise AssertionError(("timeout", tag))

    def bag(p, op=0, source=0, destination=0, state=None, status=b"committed"):
        time.sleep(.22)  # inside the shared inventory request budget
        if not op:
            p.send(32, b"")
            return fields(first(wait(p, 33, lambda d: first(d, 2) == b"ok"), 3))
        serial[0] += 1
        records = state[6] if op == 6 else state[5]
        p.send(32, integer(1, op) + blob(2, f"pq317-{serial[0]}") + integer(3, first(state, 1)) + integer(4, source)
               + integer(5, destination) + integer(6, first(fields(records[source]), 1)))
        d = wait(p, 33)
        assert first(d, 2) == status, (status, d)
        return fields(first(d, 3))

    def slot_of(state, item):
        found = [i for i, r in enumerate(state[5]) if first(fields(r), 2) == item.encode()]
        assert found, (item, state)
        return found[0]

    def keys(p, entity):
        return list(first(p.entities.get(entity, {}), 20, b""))

    def glow_client(config, capture, other, extra=None):
        """The test client with only the glow and effect harnesses, capturing at
        PEAK of its glow clock; the other player stands at AHEAD. `extra`
        adds to its environment (PQ-359: the attachment harness)."""
        lines = []
        proc = subprocess.Popen(
            ["build/client/n3e-test-client", str(package), "--connect", f"localhost:{listen}", "--ca",
             "deploy/local/ca.pem", "--auto-login", "--world-smoke", "6", "--capture", str(capture)],
            env={**os.environ, "N3E_TEST_ACCOUNT": "archer", "N3E_TEST_PASSWORD": passwords["archer"],
                 "N3E_TEST_EQUIPMENT_GLOW": "1", "N3E_TEST_EQUIPMENT_GLOW_CAPTURES": f"{PEAK}",
                 "N3E_TEST_APPEARANCE_EFFECTS": "1", "N3E_TEST_APPEARANCE_TAIL_THIN": "1", "XDG_CONFIG_HOME": config,
                 **(extra or {})},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        reader = threading.Thread(target=lambda: lines.extend(proc.stdout), daemon=True)
        reader.start()
        while proc.poll() is None:
            other.pump(.1)
        reader.join(10)
        text = "".join(lines)
        capture.with_suffix(".log").write_text(text)
        assert proc.returncode == 0, (proc.returncode, text[-1500:])
        return text

    def glow_check(text, mine, other, out, b, client):
        """PQ-337: the bow's key glow on the plug's whole model (2233 0042de90,
        00430f40), for both players, on each wearer's glow clock; a second client
        with [Addition2233] EquipmentGlow=0 at the same clock second shows the
        bow unlit by it."""
        start = rf"^PLUG_GLOW entity=(\d+) self=(\d) key={KEY} entry={ENTRY} wave=pulse modulate=2 color=1,1,1 " \
                rf"vertices=(\d+)$"
        glowing = {int(e): (int(s), int(v)) for e, s, v in re.findall(start, text, re.M)}
        assert glowing == {mine: (1, len(fixture().mesh()[1])), other: (0, len(fixture().mesh()[1]))}, \
            (glowing, text[-2000:])
        samples = [(int(e), float(t), float(i)) for e, t, i in re.findall(
            rf"^PLUG_GLOW_SAMPLE entity=(\d+) key={KEY} t=([0-9.e+-]+) intensity=([0-9.e+-]+)$", text, re.M)]
        for wearer in (mine, other):
            got = [(t, i) for e, t, i in samples if e == wearer]
            assert len(got) >= 8 and all(abs(i - glow_live.expected(t)) < 1e-3 for t, i in got), (wearer, got)
        phases = {"rise" if c < 1 else "hold" if c <= 3 else "fall" if c < 5 else "off"
                  for e, t, _ in samples if e == mine for c in [math.fmod(t, 5.5)]}
        assert {"rise", "hold", "fall"} <= phases, (phases, samples)
        print(f"PASS the client hands the bow key's equipment glow to the skeletal plug on itself and on the other "
              f"player (PLUG_GLOW: pulse at 2x over all {len(fixture().mesh()[1])} vertices); {len(samples)} "
              f"intensity samples follow 0056ea30's pulse through {sorted(phases)} on each wearer's clock", flush=True)

        def peak(log):
            made = re.findall(r"^EQUIPMENT_GLOW_CAPTURE at=([0-9.]+) drawn=[0-9.e+-]+ path=(.+)$", log, re.M)
            assert [float(t) for t, _ in made] == [PEAK], (made, log[-1500:])
            return Path(made[0][1])
        lit = peak(text)
        found = {}
        for at, e, box in re.findall(rf"^EQUIPMENT_GLOW_BOX at=([0-9.]+) entity=(\d+) self=\d key={KEY} box=(\S+)$",
                                     text, re.M):
            if float(at) == PEAK:
                found[int(e)] = tuple(int(v) for v in box.split(","))
        assert set(found) == {mine, other}, (found, text[-1500:])
        walk(b, *AHEAD)
        with tempfile.TemporaryDirectory(dir=OUT) as config:
            Path(config, "n3e").mkdir()
            Path(config, "n3e", "Option.ini").write_text("[Addition2233]\nEquipmentGlow=0\n")
            quiet = client(config, out / "bow-glow-off.ppm")
        assert "PLUG_GLOW " not in quiet and "off by Option.ini" in quiet, quiet[-1500:]
        unlit = peak(quiet)
        groups = [g for g in glow_live.brighter(lit, unlit) if g[0] >= 30]
        width, height, on = npc_looks_live.read_ppm(lit)
        _, _, off = npc_looks_live.read_ppm(unlit)

        def white(pixels, box):
            x0, y0, x1, y1 = box
            return sum(all(pixels[(y * width + x) * 3 + c] >= WHITE for c in range(3))
                       for y in range(max(0, y0), min(height, y1 + 1)) for x in range(max(0, x0), min(width, x1 + 1)))
        report = {}
        for wearer, box in found.items():
            near = [g[0] for g in groups if glow_live.overlap(g[1], box)]
            gained = white(on, box) - white(off, box)
            # The emissive alone would leave the grey 128 bow at 128 with 1x; only
            # the 2x lifts it to WHITE.
            assert near and gained >= LIFTED, (wearer, box, near, gained, groups)
            report[wearer] = (box, near, gained)
        print(f"PASS graphical client draws the glow on the skeletal bow of the local and the other player: at "
              f"{PEAK} s of the glow clock (the pulse held at 1) the bow boxes {[report[mine][0], report[other][0]]} "
              f"hold {[report[mine][1], report[other][1]]} px brighter than with EquipmentGlow=0 and gain "
              f"{[report[mine][2], report[other][2]]} px at or above {WHITE} (the 2x); {lit}, {unlit}", flush=True)
        return lit

    def effect_check(text, mine, other, lit, b, client):
        """PQ-339: the bow key's weapon effect on both players, none with
        [WeaponEffect] EffectVisible=0."""
        line = rf"^APPEARANCE_EFFECT entity=(\d+) self=(\d) key={KEY} copies=3 vertices=12 tails=2 trace={POISON:x} "
        drawn = {int(e): int(s) for e, s in re.findall(line, text, re.M)}
        assert drawn == {mine: 1, other: 0}, (drawn, re.findall(r"^APPEARANCE_EFFECT.*$", text, re.M))
        walk(b, *AHEAD)
        with tempfile.TemporaryDirectory(dir=OUT) as config:
            Path(config, "n3e").mkdir()
            Path(config, "n3e", "Option.ini").write_text("[WeaponEffect]\nEffectVisible=0\n")
            quiet = client(config, out / "bow-effect-off.ppm")
        assert "APPEARANCE_EFFECT" not in quiet and "PLUG_GLOW " in quiet, quiet[-1500:]
        hidden = Path(re.findall(r"^EQUIPMENT_GLOW_CAPTURE at=[0-9.]+ drawn=[0-9.e+-]+ path=(.+)$", quiet, re.M)[0])
        on, _ = effects_live.clusters(lit)
        off, _ = effects_live.clusters(hidden)
        # Two glows, the local player's nearer the camera (larger, lower).
        assert len(on) >= 2 and on[0][1] > on[1][1] and not off, (on, off)
        print(f"PASS graphical client draws the weapon effect on the skeletal bow's key on the local and the other "
              f"player (APPEARANCE_EFFECT: three copies, two tails): {len(on)} magenta glows {[n for n, _ in on]} px "
              f"at {PEAK} s, none with WeaponEffect.EffectVisible=0; {lit}, {hidden}", flush=True)
        # PQ-341: the tail, two green patches beside the crosses; the reverse
        # comparison (EffectVisible=0 against the effect) has none.
        tail, back = greener(lit, hidden), greener(hidden, lit)
        # One beside each player's glow: a patch whose top lies within NEAR rows
        # of the glow's, a different patch for each.
        beside = [{n for n, (_, top) in enumerate(tail) if abs(top - glow) <= NEAR} for _, glow in on[:2]]
        assert all(beside) and len(beside[0] | beside[1]) >= 2 and not back, (tail, on, back)
        print(f"PASS graphical client draws the 2233 weapon effect's tail on the local and the other player (the "
              f"synthetic tail cooked by ko_fx_tail_2233: a 20 s clip of two 10 s links, two turning meshes and two "
              f"particle parts): green patches (px, top row) {tail} beside the glows {on[:2]}, at least {GREEN} greener than "
              f"EffectVisible=0 at {PEAK} s, "
              f"none the other way", flush=True)
        # PQ-342: the red part (RED_RULE: near SPLIT, far 8.4 m) is drawn beside the local
        # player's glow, within near, and nowhere for the other, past far.
        red, red_back = greener(lit, hidden, 0), greener(hidden, lit, 0)
        nearest = [min((0, 1), key=lambda k: abs(top - on[k][1])) for _, top in red]
        assert red and nearest == [0] * len(red) and not red_back, (red, on[:2], red_back)
        print(f"PASS graphical client thins the 2233 tail's particles by the camera's distance (PQ-342, 2233 "
              f"00592900): the red part (near {RED_RULE[0]} m, far {RED_RULE[1]} m) draws patches (px, top row) {red} "
              f"at least {GREEN} redder than EffectVisible=0 beside the local player's glow {on[0]} and none beside the "
              f"other's {on[1]}, nor the other way", flush=True)

    def thin_check(text, mine, other):
        """PQ-342: the client's N3E4 rule state on each tail link
        (APPEARANCE_TAIL_THIN): every target is 2233's for the printed
        distance; the local player's tail lies within near and draws its pool;
        the other's, while it stands at AHEAD, lies past near: the green parts (40/70 m) draw their pool,
        the lime part (far 12 m) a target of 1 or 2 and at most 3 drawn with
        the earlier link's taken live ones (one more than the highest), the red part (RED_RULE[1], 8.4 m) a negative target and nothing drawn."""
        lines = [dict(entity=int(m[1]), rule=int(m[2]), count=int(m[3]), near=float(m[4]), far=float(m[5]),
                      link=float(m[6]), age=float(m[7]), distance=float(m[8]), target=int(m[9]), drawn=int(m[10]),
                      carried=int(m[11]), copy=int(m[12])) for m in re.finditer(
            r"^APPEARANCE_TAIL_THIN entity=(\d+) self=\d rule=(\d+) texture=\d+ count=(\d+) near=(\S+) far=(\S+) "
            r"link=(\S+) age=(\S+) distance=(\S+) target=(-?\d+) drawn=(\d+) carried=(\d+) copy=(\d+)$", text, re.M)]
        rules = {(l["rule"], l["near"], l["far"], l["count"]) for l in lines}
        assert rules == {(0, 40, 70, 12), (1, SPLIT, LIME_RULE[1], 12), (2, SPLIT, RED_RULE[1], 12)}, rules

        def target(l):
            d = l["distance"]
            return l["count"] if d < l["near"] else int((l["far"] - d) / l["far"] * l["count"])
        assert all(l["target"] == target(l) for l in lines if abs(l["distance"] - l["near"]) > 1e-3), \
            [l for l in lines if l["target"] != target(l)]
        report = {}
        for wearer in (mine, other):
            got = [l for l in lines if l["entity"] == wearer]
            if wearer == other:
                # While it stands at AHEAD: its first link's first STANDING s
                # (it walks aside after the B capture, nearer the camera).
                first_link = min(l["link"] for l in got)
                got = [l for l in got if l["link"] == first_link and l["age"] <= STANDING]
            assert len(got) >= 30, (wearer, len(got))
            far_ = [l["distance"] for l in got]
            report[wearer] = {k: (sorted({l["target"] for l in got if l["rule"] == k}),
                                  max(l["drawn"] for l in got if l["rule"] == k)) for k in (0, 1, 2)}
            report[wearer]["distance"] = (round(min(far_), 2), round(max(far_), 2))
            if wearer == mine:
                assert max(far_) < SPLIT and all(l["target"] == 12 for l in got), report[wearer]
            else:
                assert min(far_) > RED_RULE[1] and all(l["drawn"] == 0 and l["target"] < 0 for l in got
                                                       if l["rule"] == 2), report[wearer]
                assert all(l["target"] == 12 for l in got if l["rule"] == 0), report[wearer]
                # Taken ones live on when the target falls (2 at AHEAD, 1 aside);
                # a link counts the earlier link's taken live ones (carried).
                assert all(l["target"] in (1, 2) and l["drawn"] + l["carried"] <= 3 and l["copy"] <= 3
                           for l in got if l["rule"] == 1), report[wearer]
        # Within near the lime part draws more than the other's target allows.
        assert report[mine][1][1] > 3 and report[mine][2][1] > 0, report
        print(f"PASS the client takes the 2233 tail's particle candidates by 00592900's rule (PQ-342): "
              f"{len(lines)} samples of three N3E4 rules, every target trunc(count x (far - d) / far) past near; the "
              f"local player's tail at {report[mine]['distance']} m (within {SPLIT} m) draws each pool (most drawn "
              f"{[report[mine][k][1] for k in (0, 1, 2)]}); the other's at {report[other]['distance']} m: green "
              f"targets {report[other][0][0]}, lime {report[other][1][0]} (at most {report[other][1][1]} drawn), red "
              f"{report[other][2][0]} (none drawn)", flush=True)

    def light_check(b):
        """PQ-359: the unglowing bow takes its wearer's part light. The archer
        also wears the blade, whose quad has the bow's normal; with the glow
        and the effects off, the bow's grey over its 128 texel equals the
        blade's over its white one (the detail shader adds the white world
        slot as the blade's second layer)."""
        a = peer("archer", new=False)
        state = bag(a)
        state = bag(a, 5, slot_of(state, BLADE), 0, state)
        wait(a, 10, lambda _: sorted(keys(a, a.id)) == [BLADE_KEY, KEY])
        a.logout()
        walk(b, *AHEAD)
        with tempfile.TemporaryDirectory(dir=OUT) as config:
            Path(config, "n3e").mkdir()
            Path(config, "n3e", "Option.ini").write_text("[Addition2233]\nEquipmentGlow=0\n[WeaponEffect]\nEffectVisible=0\n")
            text = glow_client(config, out / "bow-light.ppm", b,
                               {"N3E_TEST_ATTACHMENTS": "1", "N3E_TEST_ATTACHMENT_CAPTURES": f"{LIGHT_AT}"})
        assert "PLUG_GLOW " not in text and "APPEARANCE_EFFECT " not in text, text[-1500:]
        made = re.findall(r"^ATTACHMENT_CAPTURE at=([0-9.]+) drawn=[0-9.e+-]+ path=(.+)$", text, re.M)
        assert [float(t) for t, _ in made] == [LIGHT_AT], (made, text[-1500:])
        shot = Path(made[0][1])

        def box(pattern):
            found = [tuple(int(v) for v in g.split(",")) for g in re.findall(pattern, text, re.M)]
            assert len(found) == 1, (pattern, found, text[-1500:])
            return found[0]
        bow_box = box(rf"^ATTACHMENT_BOX at={LIGHT_AT:g} entity=\d+ self=1 entry={ENTRY} box=(\S+)$")
        blade_box = box(rf"^ATTACHMENT_PART_BOX at={LIGHT_AT:g} entity=\d+ self=1 key={BLADE_KEY} box=(\S+)$")
        width, height, pixels = npc_looks_live.read_ppm(shot)

        def grey(inside, outside):
            """The commonest grey (channels within 2) inside one box and not
            the other, and how many pixels hold it."""
            counts = {}
            x0, y0, x1, y1 = inside
            for y in range(max(0, y0), min(height, y1 + 1)):
                for x in range(max(0, x0), min(width, x1 + 1)):
                    if glow_live.overlap((x, y, x, y), outside):
                        continue
                    r, g, b_ = pixels[(y * width + x) * 3:(y * width + x) * 3 + 3]
                    if max(r, g, b_) - min(r, g, b_) <= 2 and g > 8:
                        counts[g] = counts.get(g, 0) + 1
            assert counts, (inside, outside)
            value = max(counts, key=counts.get)
            return value, counts[value]
        bow_grey, bow_count = grey(bow_box, blade_box)
        blade_grey, blade_count = grey(blade_box, bow_box)
        bow_factor, blade_factor = bow_grey / fixture().GREY, blade_grey / 255
        assert bow_count >= 30 and blade_count >= 30, (bow_count, blade_count)
        assert abs(bow_factor - blade_factor) <= LIGHT_TOLERANCE, (bow_factor, blade_factor, bow_box, blade_box, shot)
        print(f"PASS graphical client lights the unglowing skeletal bow with its wearer's part light (PQ-359): with "
              f"EquipmentGlow=0 and EffectVisible=0 at {LIGHT_AT} s the bow (box {bow_box}) draws grey {bow_grey} over "
              f"its {fixture().GREY} texel ({bow_count} px), light factor {bow_factor:.3f}, and the blade quad with "
              f"the same normal (box {blade_box}) grey {blade_grey} over its white texel ({blade_count} px), "
              f"{blade_factor:.3f}; {shot}", flush=True)

    def greener(a, b, channel=1):
        """PQ-341: 4-connected patches of at least PATCH pixels at least GREEN
        greener in capture `a` than in `b`, red and blue within TINT of `b`'s
        (green added, not magenta taken away), in the middle rows (away from
        the HUD bars): (size, top row), largest first. PQ-342: `channel` 0
        for redder (green and blue within TINT)."""
        width, height, pa = npc_looks_live.read_ppm(a)
        _, _, pb = npc_looks_live.read_ppm(b)
        mask = set()
        others = [c for c in range(3) if c != channel]
        for y in range(height // 10, height * 9 // 10):
            for x in range(width):
                i = (y * width + x) * 3
                if pa[i + channel] - pb[i + channel] >= GREEN and all(abs(pa[i + c] - pb[i + c]) <= TINT for c in others):
                    mask.add((x, y))
        sizes = []
        while mask:
            stack, size, top = [mask.pop()], 0, None
            while stack:
                x, y = stack.pop()
                size += 1
                top = y if top is None else min(top, y)
                for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if n in mask:
                        mask.remove(n)
                        stack.append(n)
            if size >= PATCH:
                sizes.append((size, top))
        return sorted(sizes, reverse=True)

    def walk(p, x, z):
        end = time.monotonic() + 30
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
                return
            p.move(dx / max(1, d), dz / max(1, d), mode=1)
        raise AssertionError(("blocked", x, z, p.entities[p.id]))

    try:
        for suffix, image, port, extra in [
            ("", npc_looks_live.POSTGRES, 5432, ["-e", "POSTGRES_USER=n3e", "-e", "POSTGRES_PASSWORD=test-only",
                                                 "-e", "POSTGRES_DB=n3e", *DISPOSABLE_POSTGRES]),
            ("-redis", npc_looks_live.REDIS, 6379, []),
        ]:
            run("docker", "run", "--rm", "-d", "--name", name + suffix, *extra, "-p", f"127.0.0.1::{port}", image)
            containers.append(name + suffix)
        pg = wait_postgres(name)
        redis = run("docker", "port", name + "-redis", "6379").split()[0]
        listen, health = free_ports(2)
        env = dict(os.environ, DATABASE_URL=f"host=127.0.0.1 port={pg} user=n3e password=test-only dbname=n3e",
                   REDIS_ADDRESS=redis, N3E_PACKAGE=str(package), N3E_REALM="test-" + name,
                   N3E_LISTEN=f"127.0.0.1:{listen}", N3E_HEALTH=f"127.0.0.1:{health}")
        run(server_binary, "migrate", env=env)
        run(server_binary, "convert-progression", env={**env, "N3E_TEST_PROGRESSION": "disposable"})
        for account, password in passwords.items():
            run(server_binary, "account-create", account, env=env, stdin=password + "\n")
        log = open(out / "server.log", "w")
        server = subprocess.Popen([server_binary], env=env, stdout=log, stderr=log)
        deadline = time.monotonic() + 30
        while True:
            assert server.poll() is None, (out / "server.log").read_text()[-2000:]
            assert time.monotonic() < deadline, "server never reported ready"
            try:
                if urllib.request.urlopen(f"http://127.0.0.1:{health}/ready", timeout=0.2).status == 200:
                    break
            except OSError:
                time.sleep(0.1)

        def peer(account, new=True):
            p = Peer(listen, account, passwords[account], content=(package / "release.sha256").read_text().strip(),
                     game=manifest["game_id"], protocol=manifest["protocol_version"])
            if new:
                p.create(account.title())
            assert p.select(p.characters[0][0])[0] == 10
            return p
        a = peer("archer")
        state = bag(a)
        assert len(state[6]) == 6, state[6]  # two hand and two ring slots, then Wing and Fairy
        # The server alone decides where the bow may be worn: not in the right
        # hand, not in the wing slot; the refused requests change no key.
        bag(a, 5, slot_of(state, BOW), 0, state, status=b"incompatible_slot")
        bag(a, 5, slot_of(state, BOW), 4, state, status=b"incompatible_slot")
        a.pump(.3)
        assert keys(a, a.id) == [], keys(a, a.id)
        state = bag(a, 5, slot_of(state, BOW), 1, state)
        wait(a, 10, lambda _: keys(a, a.id) == [KEY])
        a.logout()
        a = peer("archer", new=False)
        assert first(fields(bag(a)[6][1]), 2) == BOW.encode()
        wait(a, 10, lambda _: keys(a, a.id) == [KEY])
        a.logout()
        b = peer("companion")
        b_state = bag(b)
        b_state = bag(b, 5, slot_of(b_state, BOW), 1, b_state)
        wait(b, 10, lambda _: keys(b, b.id) == [KEY])
        walk(b, *AHEAD)
        print(f"PASS the server refuses the bow in the right hand and in the wing slot; both accounts equip it in "
              f"the left hand over the wire, carry appearance key {KEY}, and it stays equipped across sessions; "
              f"the companion stands at {AHEAD}", flush=True)
        if os.environ.get("N3E_GRAPHICAL") != "1":
            b.logout()
            return

        lines = []
        capture = out / "bow.ppm"
        with tempfile.TemporaryDirectory(dir=OUT) as config:
            proc = subprocess.Popen(
                ["build/client/n3e-test-client", str(package), "--connect", f"localhost:{listen}", "--ca",
                 "deploy/local/ca.pem", "--auto-login", "--world-smoke", "20", "--capture", str(capture)],
                env={**os.environ, "N3E_TEST_ACCOUNT": "archer", "N3E_TEST_PASSWORD": passwords["archer"],
                     "N3E_TEST_ATTACHMENTS": "1", "N3E_TEST_ATTACHMENT_CAPTURES": f"{A},{B}",
                     "N3E_TEST_EQUIPMENT_GLOW": "1", "N3E_TEST_EQUIPMENT_GLOW_CAPTURES": f"{PEAK}",
                     "N3E_TEST_APPEARANCE_EFFECTS": "1", "N3E_TEST_APPEARANCE_TAIL_THIN": "1",
                     "XDG_CONFIG_HOME": config},
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            reader = threading.Thread(target=lambda: lines.extend(proc.stdout), daemon=True)
            reader.start()
            walked = cast = False
            while proc.poll() is None:
                b.pump(.1)
                if not walked and re.search(rf"^ATTACHMENT_CAPTURE at={B} ", "".join(lines), re.M):
                    walk(b, *ASIDE)
                    b.pump(1.5)
                    walked = True
                    # The companion casts the fixture's heal on itself (1.5 s).
                    cast = b.action(b.id, action=manifest["skills"]["skills"][0]["id"])
            reader.join(10)
        text = "".join(lines)
        capture.with_suffix(".log").write_text(text)
        assert proc.returncode == 0, (proc.returncode, text[-1500:])
        assert walked and cast == "cast_pending", (cast, text[-1500:])
        made = re.findall(r"^ATTACHMENT_CAPTURE at=([0-9.]+) drawn=[0-9.e+-]+ path=(.+)$", text, re.M)
        assert [float(t) for t, _ in made] == [A, B], (made, text[-1500:])
        shown = [Path(p) for _, p in made]
        other = b.id
        start = rf"^ATTACHMENT entity=(\d+) self=(\d) key={KEY} entry={ENTRY} group=2 joint=1 vertices=(\d+) lit=0 " \
                rf"modulate=1 emissive=0$"
        drawn = {int(e): (int(s), int(v)) for e, s, v in re.findall(start, text, re.M)}
        mine = [e for e, (s, _) in drawn.items() if s == 1]
        assert len(mine) == 1 and other in drawn and len(drawn) == 2, (drawn, text[-2000:])
        assert all(v == len(bow.mesh()[1]) for _, v in drawn.values()), drawn
        mine = mine[0]
        samples = [s for s in plug_samples(text) if s["entry"] == ENTRY]
        report = {}
        for wearer in (mine, other):
            got = [s for s in samples if s["entity"] == wearer]
            assert len(got) >= 6, (wearer, len(got), text[-2000:])
            # Slot 0 standing and walking aside; slot 2 only while the other casts.
            assert {s["slot"] for s in got} == ({0} if wearer == mine else {0, 2}), (wearer, {s["slot"] for s in got})
            # The skinned model is the fixture's bow at the sampled clip time,
            # and its drawn vertices sit where the joint and the placement put it.
            worst = 0.0
            for s in got:
                assert all(abs(s["model"][k] - bow.centre(s["slot"], s["time"])[k]) < 2e-3 for k in range(3)), s
                expect = frame(s)
                worst = max(worst, math.dist(expect, s["placed"]))
                assert math.dist(expect, s["placed"]) < 2e-3, (expect, s)
            times = sorted({round(s["time"], 2) for s in got if s["slot"] == 0})
            sway = max(s["model"][0] for s in got if s["slot"] == 0) - min(s["model"][0] for s in got if s["slot"] == 0)
            assert len(times) >= 4 and sway > .03, (wearer, times, sway)
            report[wearer] = dict(samples=len(got), times=len(times), sway=round(sway, 3), worst=worst)
        walking = [s for s in samples if s["entity"] == other
                   and math.hypot(s["wearer"][0] - ASIDE[0], s["wearer"][2] - ASIDE[1]) < .4]
        assert walking, [s["wearer"] for s in samples if s["entity"] == other]
        clips = re.findall(rf"^ATTACHMENT_CLIP entity={other} entry={ENTRY} clip=(\d)$", text, re.M)
        assert clips == ["0", "2", "0"], clips
        magic = [s for s in samples if s["entity"] == other and s["slot"] == 2]
        assert magic and all(0 <= s["time"] <= bow.CLIPS[2]["duration"] + 1e-6 for s in magic), magic
        # Once and held (2233 0042e070 with the once flag): the cast's samples,
        # in order, never go back, and the last is at the clip's end. A looping
        # slot would wrap back within the 1.5 s cast.
        held = [s["time"] for s in magic]
        assert len(held) >= 2 and all(b >= a for a, b in zip(held, held[1:])) \
            and abs(held[-1] - bow.CLIPS[2]["duration"]) < 1e-4, (held, bow.CLIPS[2]["duration"])
        mine_clips = re.findall(rf"^ATTACHMENT_CLIP entity={mine} entry={ENTRY} clip=(\d)$", text, re.M)
        assert mine_clips == ["0"], mine_clips
        print(f"PASS the client draws the bow on itself and on the other player: lit 0, modulate 1, no emissive; "
              f"every sampled centre of its drawn vertices is the wearer x joint x placement of the skinned model "
              f"(worst {max(r['worst'] for r in report.values()):.1e}), which is the fixture's bow at the sampled "
              f"clip time; slot 0 plays on its own clock ({[(r['samples'], r['times'], r['sway']) for r in report.values()]}"
              f" samples, distinct times, sway in x), keeps playing while the other walks aside, and the other's "
              f"cast plays slot 2 once and holds its end ({held} s) before slot 0 again", flush=True)
        boxes = {}
        for at in (A, B):
            for e, n, box in re.findall(rf"^ATTACHMENT_BOX at={at} entity=(\d+) self=\d entry=(\d+) box=(\S+)$",
                                        text, re.M):
                if int(n) == ENTRY:
                    x0, y0, x1, y1 = (int(v) for v in box.split(","))
                    old = boxes.get(int(e), (x0, y0, x1, y1))
                    boxes[int(e)] = (min(old[0], x0), min(old[1], y0), max(old[2], x1), max(old[3], y1))
        assert set(boxes) == {mine, other}, (boxes, mine, other)
        shares = {e: swing(shown[0], shown[1], box) for e, box in boxes.items()}
        assert min(shares.values()) >= SWING, (shares, boxes)
        print(f"PASS graphical client draws the animated skeletal bow on the local and the other player: in the bow "
              f"boxes {[boxes[mine], boxes[other]]} {[shares[mine], shares[other]]} of the pixels differ between "
              f"{A} s and {B} s, the sway's two extremes; {shown[0]}, {shown[1]}", flush=True)
        client = lambda config, capture: glow_client(config, capture, b)  # noqa: E731
        lit = glow_check(text, mine, other, out, b, client=client)
        effect_check(text, mine, other, lit, b, client=client)
        thin_check(text, mine, other)
        light_check(b)
        b.logout()
    finally:
        if server is not None:
            server.kill()
            server.wait()
        if log is not None:
            log.close()
        for c in containers:
            container_logs({name: "postgres", name + "-redis": "redis"}[c], ["docker", "logs", "--timestamps", c])
        for c in containers:
            subprocess.run(["docker", "rm", "-f", c], capture_output=True)


if __name__ == "__main__":
    os.chdir(ROOT)
    package = prepare()
    assert (package / "attachments.bin").read_bytes()[:4] == b"N3AT"
    refused = check_readers(package)
    print(f"PASS N3AT skeletal plug package: both readers accept it; {refused} malformed packages are refused",
          flush=True)
    live(package)
