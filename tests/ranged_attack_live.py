"""PQ-416, PQ-420: a ranged basic attack on a combat profile (N3RB/N3RC, D-216, D-217), live.

1298's bow attack is the archery cast, not a swing: the auto-attack tick
(KnightOnLine.exe 004659b0, 00465fd5) never walks; it calls the skill start
005819e0 once an interval, whose range check 00583780 measures the 3-D distance
against the bow's range plus both radii (and posts text 0xfa9 when it fails),
and the cast start 00583f20 stops the walk (005844c2). n3e expresses it as a
package rule: ranged-attack.bin names a combat profile, its strike range is
both radii summed plus the profile's range in 3-D, checked by the server, and
the client never chases into melee reach under it. Evidence:
docs/implementation/evidence/pq-416-bow-archery-rules.md.

The package is the PQ-249 fixture (tests/npc_templates_live.py: melee radii 1
and 1, the blade selecting combat profile 2) with profile 2 a ranged attack of
range 8 and reach 6 (strike limit 10 m, click walk 7 m), and two passive,
motionless templates, NEAR 6 m and FAR 15 m in front of the player spawn.

PQ-420 (D-217): profile 2 also has a cast time, 900 ms, and its own attack
clip (1 s, blend 0.2 s, first marker 0.8 s), as 1298's archery cast
(00583f20, 00461ab0 stretching the start clip over the cast time, 00585830
ending it at the clip's marker, 004689f0, and cancelling it on a walk). The
server holds each shot and lands it 0.2 + 0.8 x 0.9 = 0.92 s, 19 ticks,
after accepting it (its wear write commits first, as every strike's does;
since PQ-421 a shot that spends an arrow starts that commit a tick before
the landing, so its hit is published at the landing tick; the profile's
interval is 2000 ms here): the archer's strike fields show the cast from the
acceptance (strike_result "casting", the target unharmed), the hit comes at
the landing as a kind-6 event and the result then; a second shot while one is
held is refused, a movement input after the acceptance cancels the shot
(`interrupted`, no damage, the cast cleared), one queued before it does not.

PQ-421 (D-218): profile 2 also needs ammunition, as 1298's archery needs
arrows (client 0057f7f0 refuses the cast without them, text 0xfa7; Ebenezer's
flying phase 0046f3f1 removes them through 004b0792): a synthetic arrow item
(stack 20, ARROWS granted at start), one per shot. Each shot that lands
removes one from the archer's bag in its durable wear commit, a cancelled or
refused one none (PQ-444: a released one at its release, below); with none
left the server refuses the shot (`no_ammo`, NEAR unharmed, no interval
spent), and the empty bag survives a new login. With
N3E_GRAPHICAL=1 a third archer's client counts its arrows down shot by shot,
and the first archer's, now without arrows, neither shoots nor walks but posts
the package's ammo notice once an interval (RANGED_NO_AMMO).

PQ-422 (D-219): profile 2 also carries a type-2 skill hit (N3RE), as 1298's
archery is a skill whose NPC damage the AI server resolves through its type-2
leaf (0040d471 -> 00443a34's skill branch, plus the row's AddDamagePlus): the
fixture's terms (HitRate 100, AddDamage 150, AddDamagePlus 100) make every
landed shot a hit for 100 plus trunc(base x 0.6f + rand(0..base) x 0.89f +
0.99), base = trunc(150 x 0.01f x attack x 200 / 240) from the archer's
derived attack (NEAR's defence is 0), or exactly 100 on a missed grade.

PQ-417 (D-222) gave profile 2 a flight (a one-triangle arrow from joint 0 and
a hit clip). PQ-439 (D-223): the server releases each held shot at its
landing tick (a kind-7 event; the archer's strike_result 'released') and
lands it when its arrow arrives, the 3-D distance over the flight's speed (4
m/s here) later, as 1298's NPC loses HP only when the shooter's client reports
the arrow's collision (0047a8d0 -> the effecting phase, Ebenezer 004630a6 ->
AI 0040d471). Released, a movement no longer cancels it; once the interval
has run the next shot is accepted while the arrow flies, and the earlier
landing leaves its cast alone; a release that finds the previous arrow still
in the air waits for it. The client launches the arrow at the release and
sends its next shot once the interval has run.

PQ-444 (D-224): the arrow is spent at the release, as Ebenezer's flying phase
(004630a6 -> 0046f3f1 -> 004b0792) spends it: the server's release makes a
durable write of its own that removes it (no roll), and releases the shot
when that write commits; the arrival commits only the wear. So the archer's
bag drops at the release, before the arrival; a shot cancelled in flight (the
archer's profile changed) has spent its arrow; a release whose write finds
too few arrows in the locked durable bag fails `no_ammo` with no release; a
slow release write delays the release; and the client's count drops before
its next shot while the previous arrow flies. The blade is durable enough here
(3000) that every hit wears it, so every arrival also makes a wear commit.

PQ-447 (D-227): once a shot is released, a skill (the fixture's heal) and
rest start while its arrow flies, as 1298's skill start and sit command test
the cast, not the arrow (005819e0, 005d91f0) and Ebenezer neither (004630a6,
004a8ad1); the arrow lands during the cast and under the seated archer, who
stays seated.

PQ-454 (D-228): the basic attack here costs COST resource, which a shot with a
flight pays at its release, as Ebenezer's flying phase takes the row's Msp
(0046f3f1 -> 004a083f) and its effecting phase does not check it again for a
row with a flight (00464b43): the archer's resource drops at the release, and
not at the arrival, so a skill's impact during the flight cannot leave the
arrival unpaid.

PQ-467 (D-233): profile 2 also has a hold (N3RH), 10.5 m on the ground plane,
as Ebenezer's magic packet checks the range on each phase of an archery row
(004630a6 -> 004c1dbe at 004635c8, the flying and effecting phases
included; Type1 2: dx^2 + dz^2 at most (item range / 10)^2 + 1000.0): an
archer that walks away from a 9.5 m shot after its release stands beyond it
when the arrow arrives, and the shot fails out_of_range then, NEAR unharmed,
its arrow already spent.

Both readers must accept it. Against a native server on a disposable Postgres
and Redis, over the wire: unarmed (the melee profile) the archer's strike at
NEAR is refused out of range; with the blade worn its combat style is the
ranged profile, a strike at FAR is refused and one at NEAR, 6 m away, is
accepted without the archer moving, never as a moving strike even with a
movement queued beside it; the next try inside the interval is refused as
cooldown; at 9.5 m from NEAR (3-D) it is accepted and at 10.5 m refused. With
N3E_GRAPHICAL=1 the real test client logs in as the archer at the spawn and
presses Z and R: it must shoot NEAR from where it stands (RANGED_SHOT, server
strikes on NEAR, no movement), and as a second archer 16 m from NEAR it must
not walk, shoot or swing, but post the package's notice once an interval
(RANGED_TOO_FAR).
"""
import json
import math
import os
from pathlib import Path
import re
import shutil
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
import npc_looks_live  # noqa: E402

OUT = ROOT / "build/pq416"
PLAYER = (-5.0, -5.0)
NEAR, FAR = [-5.0, -11.0], [-5.0, -20.0]
# Where the second archer stands: 16 m from NEAR, 25 m from FAR.
SPOT = (-5.0, 5.0)
# PQ-423: where the third archer shoots from, 6 m from NEAR off the z axis
# (13.9 m from FAR), so it faces NEAR at a heading of pi/4, not 0.
BOW_SPOT = (NEAR[0] + 6 / math.sqrt(2), NEAR[1] + 6 / math.sqrt(2))
# PQ-445: where the bowman shoots from when its arrow must reach NEAR before
# the release event: 1.8 m from NEAR on the same line.
CLOSE_SPOT = (NEAR[0] + 1.8 / math.sqrt(2), NEAR[1] + 1.8 / math.sqrt(2))
RADII = 1 + 1  # the fixture's melee actor and target radii
# PQ-422: a type-2 skill hit; AddDamagePlus makes even a missed grade deal it.
SKILL_HIT = dict(hit_rate=100, add_damage=150, add_damage_plus=100)
# PQ-423 (D-220): the cast effect, a synthetic one-triangle clip on joint 0.
CAST_EFFECT = dict(clip="bow-cast", joints=[0])
CAST_TRIANGLE = [(.6, 1.0, -.8), (.8, 1.0, -.8), (.7, 1.2, -1.0)]
# PQ-417 (D-222): the flight, a synthetic one-triangle arrow (its tip 0.9 m
# along the model's forward, -z) flown from joint 0, and a one-triangle hit
# clip on the target's position. PQ-439 (D-223): at 4 m/s, slow enough that
# an arrow released at 6 m (30 ticks) is still in the air when the 40-tick
# interval lets the next shot go, and one at 9.5 m (48 ticks) when that next
# shot reaches its release.
FLIGHT = dict(clip="bow-flight", joint=0, speed=4, hit_clip="bow-hit", hit_joint=-1, release="blow")
FLIGHT_TRIANGLE = [(0, 0, -.9), (.05, 0, 0), (-.05, 0, 0)]
HIT_TRIANGLE = [(-.3, .5, 0), (.3, .5, 0), (0, 1.1, 0)]
# PQ-467 (D-233): the hold, 10.5 m on the ground plane, beyond the 10 m start
# limit so that no acceptance here meets it, but within reach of an archer
# who walks away from a 9.5 m shot while its arrow flies.
HOLD = dict(distance=10.5, plane="xz")
RANGED = dict(profile=2, reach=6, range=8, cast_ms=900, ammo=dict(item="demo:item/arrow", count=1),
              skill_hit=SKILL_HIT, cast_effect=CAST_EFFECT, flight=FLIGHT, hold=HOLD)
LIMIT = RADII + RANGED["range"]
# PQ-420: the cast clip (clip 3) and its landing: ceil((0.2 + 0.8 x 0.9) x 20).
CAST_CLIP = dict(duration=1, blend=0.2, marker=0.8)
LAND = math.ceil((CAST_CLIP["blend"] + CAST_CLIP["marker"] * RANGED["cast_ms"] / 1000 / CAST_CLIP["duration"]) * 20)
# The ranged profile's interval, longer than the fixture's 1140 ms so the
# cooldown after a landing (LAND plus the wear commit) is a wide window.
INTERVAL_MS = 2000
PAUSE = INTERVAL_MS / 1000 + .1
NOTICE = "Target too far (synthetic)"
# PQ-421: the arrows, one per shot, ARROWS of them granted at start.
ARROW = "demo:item/arrow"
# PQ-447: the fixture's heal (npc_templates_live: 1.5 s cast, self target).
HEAL = "demo:skill/heal"
ARROWS = 19  # PQ-444: 12 before; the shots below spend up to 18 (PQ-447, PQ-467)
# PQ-454 (D-228): the basic attack's cost, paid at the release, and the
# fixture's regeneration (1 resource on every REGEN-th tick).
COST, REGEN = 2, 20
AMMO_NOTICE = "Not enough arrows (synthetic)"
# Passive and motionless (npc_looks_live.BASE: defence 0), with health for
# every shot (each deals at least SKILL_HIT's plus since PQ-422).
TEMPLATES = [dict(npc_looks_live.BASE, name="demo:creature/near", looks="demo:looks/near", health=20000),
             dict(npc_looks_live.BASE, name="demo:creature/far", looks="demo:looks/far", health=20000)]


def flight_ticks(event):
    """PQ-439 (D-223): the server's flight of a release event (kind 7): the
    3-D distance between its positions (fields 11-13 and 14-16) in f32, over
    the flight's speed, x 20, rounded up (ranged_shot.rs flight_ticks)."""
    import struct

    def f32(value):
        return struct.unpack("<f", struct.pack("<f", value))[0]
    from world_peer import first
    a = [f32(first(event, k, 0.0)) for k in (11, 12, 13)]
    b = [f32(first(event, k, 0.0)) for k in (14, 15, 16)]
    square = 0.0
    for k in range(3):
        d = f32(b[k] - a[k])
        square = f32(square + f32(d * d))
    return min(200, math.ceil(f32(math.sqrt(square)) / f32(FLIGHT["speed"]) * 20))


def skill_hit_damage(attack, defense=0, hit=SKILL_HIT):
    """PQ-422 (D-219): the damages a landed type-2 shot can deal: a missed
    grade deals the plus alone, a hit the plus and trunc(base x 0.6f +
    r x 0.89f + 0.99) for r in 0..=base, base = trunc(AddDamage x 0.01f x
    (attack x 200 / (defence + 240))) (AI 00443a34's skill branch, its f32
    constants as exact rationals). Returns (miss, low, high)."""
    from fractions import Fraction
    import struct

    def f32(value):
        return Fraction(struct.unpack("<f", struct.pack("<f", value))[0])
    c099 = Fraction(struct.unpack("<d", struct.pack("<II", 0x7AE147AE, 0x3FEFAE14))[0])
    base = math.floor(hit["add_damage"] * f32(.01) * (attack * 200 // (defense + 240)))
    low = math.floor(f32(.6) * base + c099)
    high = math.floor(f32(.6) * base + f32(.89) * base + c099)
    plus = hit["add_damage_plus"]
    return plus, plus + low, plus + high
BLADE = "demo:item/blade"


@once_per_run
def prepare():
    """Cook the PQ-249 package with profile 2 a ranged attack; returns its directory."""
    from npc_templates_live import prepare as base
    sys.path.insert(0, str(ROOT / "tools/assetc"))
    import main

    source = base().parent / "source"
    root, out = OUT / "source", OUT / "package"
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(source, root)
    m = json.loads((root / "package.json").read_text())
    assert m["melee"]["actor_radius"] + m["melee"]["target_radius"] == RADII, m["melee"]
    assert m["combat_animation"]["rows"][1] == dict(items=[BLADE], profile=2), m["combat_animation"]["rows"]
    m["gameplay"].update(spawns=[NEAR, FAR], spawn_x=PLAYER[0], spawn_z=PLAYER[1])
    assert m["gameplay"]["cost"] == 0 and m["gameplay"]["regen_ticks"] == REGEN, m["gameplay"]
    m["gameplay"]["cost"] = COST
    m["npc"]["templates"] = TEMPLATES
    m["npc"]["slots"] = [dict(area=[0, 0, 0, 0], respawn_ticks=60, template=t["name"]) for t in TEMPLATES]
    # A struck NPC that cannot reach the archer gives up and goes home; without
    # the heal there it keeps its entity id (a healed one takes a fresh id,
    # gameplay.rs), so the client's target stays.
    m["npc"]["return_heal"] = False
    # PQ-420: profile 2 takes its own attack clip, which the cast stretches.
    clips = m["combat_animation"]["clips"]
    clips.append(dict(clips[1], duration=CAST_CLIP["duration"], blend=CAST_CLIP["blend"],
                      markers=[CAST_CLIP["marker"], -1]))
    m["combat_animation"]["profiles"][1].update(attacks=[len(clips) - 1], moving=len(clips) - 1)
    m["combat_animation"]["profiles"][1]["interval_ms"] = INTERVAL_MS
    # PQ-444: a blade that does not break here (it wears 3 to 5 a hit at the
    # fixture's scale 0.1), so every hit's arrival makes a wear commit.
    blade = next(i for i in m["inventory"]["items"] if i["id"] == BLADE)
    assert blade["durability"] == 3, blade
    blade["durability"] = 3000
    for drop in m["progression"]["items"]["items"]:
        if drop["id"] == BLADE:
            drop["durability"] = 3000  # a dropped blade carries the item's durability
    # PQ-421: the arrow, an ordinary stackable item that does not wear.
    assert "wear" in m and "commerce" in m, sorted(m)
    m["inventory"]["items"].append(dict(id=ARROW, label="Arrow (synthetic)", stack_limit=20, durability=0,
                                        starting=ARROWS))
    m["commerce"]["items"].append(dict(id=ARROW, weight=0, price=1, sell_divisor=6))
    m["ranged_attack"] = dict(profiles=[RANGED], notice=NOTICE, ammo_notice=AMMO_NOTICE)
    # PQ-423: the fixture's effects (npc_templates_live: a blank "cast" and
    # "heal" clip) gain the cast effect's clip: 3 s at 10 a second, each frame
    # one triangle away from its joint.
    from common import string, u
    import struct
    blank = lambda name: string(name) + u(0) + u(10) + u(1) + u(0)
    frame = u(1) + u(0) + u(0) + u(5) + u(6) + u(199) + u(3) + b"".join(
        struct.pack("<9f", *p, 0, 0, 1, 1, 1, 1) for p in CAST_TRIANGLE)
    bow = string(CAST_EFFECT["clip"]) + u(0) + u(10) + u(30) + frame * 30
    # PQ-417: the flight's clip (10 s, as 1298's bundle life) and the hit's (1 s).
    def one(points):
        return u(1) + u(0) + u(0) + u(5) + u(6) + u(199) + u(3) + b"".join(
            struct.pack("<9f", *p, 0, 0, 1, 1, 1, 1) for p in points)
    flight = string(FLIGHT["clip"]) + u(0) + u(10) + u(100) + one(FLIGHT_TRIANGLE) * 100
    hit = string(FLIGHT["hit_clip"]) + u(0) + u(10) + u(10) + one(HIT_TRIANGLE) * 10
    assert m["presentation"]["effects.bin"] == "effects.bin"
    (root / "effects.bin").write_bytes(b"N3EF" + u(1) + u(1) + u(1) + bytes(4) + u(5) + blank("cast") + blank("heal")
                                       + bow + flight + hit + u(0))
    (root / "package.json").write_text(json.dumps(m))
    main.cook(root, out)
    return out.resolve()


def cast_effects(text, starts, lands):
    """PQ-423 (D-220): the archer's client draws the cast effect from each
    held shot's start (RANGED_CAST_FX start, on joint 0, as 1298's cast
    start 00583f20 triggers the row's self FX, 00479de0) and ends it at once
    when the shot is released (`lands`: by request, the release tick since
    PQ-439; RANGED_CAST_FX stop, as 00584b00 stops the self FX at the
    release, 0047a710). Since PQ-445 (D-226) the archer's own client ends it
    on the frame that launches its predicted flight, at the predicted release
    (`flights` checks that frame's lag); the strike fields that stop showing
    the cast end it only when no prediction launched; where
    it is drawn, each vertex is the joint plus the clip's record turned by the
    archer's facing (RANGED_CAST_FX draw: 00477590 faces a self FX along the
    caster's +Z). The archer stands off NEAR's z axis, so its facing is
    pi/4 and the turn is checked at a heading other than 0."""
    tick_of = {t: r for r, t in starts.items()}
    began = {int(t): float(a) for t, j, a in re.findall(
        r"^RANGED_CAST_FX start actor=\d+ self=1 tick=(\d+) request=\d+ joint=(0) age=(\S+)$", text, re.M)}
    ended = {int(t): float(a) for t, a in re.findall(
        r"^RANGED_CAST_FX stop actor=\d+ self=1 tick=(\d+) joint=0 age=(\S+)$", text, re.M)}
    shown = [(int(t), float(h), [float(v) for v in o.split(",")], [float(v) for v in b.split(",")]) for t, h, o, b in
             re.findall(r"^RANGED_CAST_FX draw actor=\d+ self=1 tick=(\d+) joint=0 vertices=3 heading=(\S+) "
                        r"offset=(\S+) base=(\S+)$", text, re.M)]
    landed = [t for t in began if t in tick_of and tick_of[t] in lands]
    assert set(began) <= set(starts.values()) and len(landed) >= 2, (began, starts, text[-2000:])
    # Each released shot's effect ends at its release. The effect starts at
    # the predicted shot's start; since PQ-445 it ends at the frame of the
    # predicted release (0.92 s in plus that frame's lag, which `flights`
    # bounds). The window, from PQ-439, also admits an end at the release
    # event: LAND ticks after the cast's start, plus the local start's lead
    # over the server's tick and a snapshot's delay.
    window = (LAND * .05 - .15, (LAND + 20) * .05 + .6)
    assert all(t in ended and window[0] <= ended[t] <= window[1] for t in landed), (began, ended, lands, window)
    base = [sum(p[k] for p in CAST_TRIANGLE) / 3 for k in range(3)]
    # The archer at BOW_SPOT faces NEAR: heading atan2(dx, dz) of archer -
    # NEAR = pi/4, so the turn is not the identity.
    assert shown and all(abs(h - math.pi / 4) < .05 for _, h, _, _ in shown), (shown, text[-2000:])
    for _, h, offset, drawn_base in shown:
        assert all(abs(a - b) < 1e-4 for a, b in zip(drawn_base, base)), (drawn_base, base)
        turned = (base[0] * math.cos(h) + base[2] * math.sin(h), base[1], -base[0] * math.sin(h) + base[2] * math.cos(h))
        assert all(abs(a - b) < 1e-3 for a, b in zip(offset, turned)), (offset, turned, h)
    print(f"PASS graphical client draws the cast effect on the archer (PQ-423): from each held shot's start on joint 0 "
          f"(RANGED_CAST_FX start, {len(began)} shots), ended at once at its release ({len(landed)} released, ended "
          f"{sorted(round(ended[t], 2) for t in landed)} s in, RANGED_CAST_FX stop), drawn at the joint plus the clip's "
          f"triangle turned by the archer's facing, pi/4 here ({len(shown)} draws, headings "
          f"{sorted({round(h, 2) for _, h, _, _ in shown})})", flush=True)


def turn_to(d):
    """D-222: the shortest turn from the model's forward (0, 0, -1) to the
    unit `d` (render/effects.h flight_rotation), as a function of a point."""
    c, kx, ky = -d[2], d[1], -d[0]
    s = math.hypot(kx, ky)
    if s < 1e-6:
        return (lambda v: v) if c > 0 else (lambda v: (-v[0], v[1], -v[2]))
    kx, ky, t = kx / s, ky / s, 1 - c
    m = [[c + kx * kx * t, kx * ky * t, ky * s], [kx * ky * t, c + ky * ky * t, -kx * s], [-ky * s, kx * s, c]]
    return lambda v: tuple(sum(m[r][k] * v[k] for k in range(3)) for r in range(3))


def local_flights(text):
    """PQ-445 (D-226): the archer's own predicted flights, by request:
    RANGED_FLIGHT local (launched on the first frame at or after the
    predicted release: `predicted`, that release's time after the shot was
    sent; `late`, how long after it the launching frame came; `age`, the
    flight's age at its launch, 0 since it starts at that frame), confirm (the
    release event found it), held (it arrived before that), cancel (the shot
    was not released) and the draw and hit lines of its flights."""
    num = lambda v: [float(x) for x in v.split(",")]
    local = {int(r): dict(target=int(tg), age=float(a), predicted=float(pr), late=float(lt), origin=num(f), d=num(d),
                          speed=float(sp), launch=float(ln), box=int(b))
             for r, tg, a, pr, lt, f, d, sp, ln, b in re.findall(
                 r"^RANGED_FLIGHT local actor=\d+ self=1 request=(\d+) target=(\d+) age=(\S+) predicted=(\S+) late=(\S+) "
                 r"from=(\S+) dir=(\S+) speed=(\S+) launch=(\S+) box=([01])$", text, re.M)}
    confirmed = {int(r): (int(t), float(lead), int(h)) for r, t, lead, h in re.findall(
        r"^RANGED_FLIGHT confirm actor=\d+ self=1 request=(\d+) tick=(\d+) lead=(\S+) held=(\d+)$", text, re.M)}
    held = {int(r): (float(reach), float(late)) for r, reach, late in re.findall(
        r"^RANGED_FLIGHT held actor=\d+ self=1 request=(\d+) target=\d+ reach=(\S+) late=(\S+) box=[01]$", text, re.M)}
    cancelled = {int(r): (float(a), int(h)) for r, a, h in re.findall(
        r"^RANGED_FLIGHT cancel actor=\d+ self=1 request=(\d+) age=(\S+) held=([01])$", text, re.M)}
    event = {int(r): int(t) for t, r in re.findall(
        r"^RANGED_FLIGHT start actor=\d+ self=1 tick=(\d+) request=(\d+) ", text, re.M)}
    drawn = [(int(r), int(t), float(a), num(an), num(o), num(b)) for t, r, a, an, o, b in re.findall(
        r"^RANGED_FLIGHT draw actor=\d+ self=1 tick=(\d+) request=(\d+) age=(\S+) vertices=3 anchor=(\S+) offset=(\S+) "
        r"base=(\S+)$", text, re.M)]
    hits = {int(r): dict(tick=int(t), target=int(tg), reach=float(re_), late=float(late), held=float(h), box=int(b), clip=c,
                         joint=int(j))
            for t, r, tg, re_, late, h, b, c, j in re.findall(
                r"^RANGED_FLIGHT hit actor=\d+ self=1 tick=(\d+) request=(\d+) target=(\d+) reach=(\S+) late=(\S+) held=(\S+) "
                r"at=\S+ box=([01]) clip=(\S+) joint=(-?\d+)$", text, re.M)}
    return local, confirmed, held, cancelled, event, drawn, hits


def flights(text, lands, target):
    """PQ-417 (D-222): the archer's client flies each released shot's arrow
    (`lands`: the release ticks by request since PQ-439, D-223), from the
    archer's joint 0 toward the centre of the target's box at the flight's
    speed, its anchor the start plus the direction x speed x age and its
    triangle turned from -z to the direction (RANGED_FLIGHT draw: 00477590
    moves a move-type-0 bundle along its direction, 0048f700 turns its parts
    to it), ending where the ray enters the target's box with the hit clip on
    the target (RANGED_FLIGHT hit: 0047a8d0 stops it at the box, 00586fa0
    triggers the target FX). PQ-445 (D-226): its own client launches it at
    its predicted release (RANGED_FLIGHT local: the shot's local start plus
    the stretched clip's blend and marker, as 1298's cast tick 00585830
    calls the release 00584b00 at the marker, which flies the arrow at once,
    005855bc -> 00587ac0), ahead of the release event, which confirms it
    (RANGED_FLIGHT confirm) and launches no second flight."""
    local, confirmed, held, cancelled, event, drawn, hits = local_flights(text)
    released = set(lands)
    assert len(released) >= 2 and released <= set(local), (lands, local, text[-2000:])
    assert not (released & set(event)) and not (released & set(cancelled)), (event, cancelled)
    predicted = CAST_CLIP["blend"] + CAST_CLIP["marker"] * RANGED["cast_ms"] / 1000 / CAST_CLIP["duration"]
    for r in released:
        f = local[r]
        assert f["target"] == target and f["box"] == 1 and f["speed"] == FLIGHT["speed"], (r, f)
        # At the drawn clip's marker (0.92 s after the shot was sent, before
        # the server's LAND-tick release), launched by the first frame after
        # it (`late`, under 0.1 s) and starting at that frame (`age` 0).
        assert abs(f["predicted"] - predicted) < 1e-4 and predicted < LAND * .05, (r, f, predicted)
        assert 0 <= f["late"] < .1 and f["age"] == 0, (r, f)
        assert abs(math.hypot(*f["d"]) - 1) < 1e-3, (r, f)
        # From the archer's joint at BOW_SPOT toward NEAR's box: the level
        # part of the direction points at NEAR, the launch about 6 m.
        aim = [f["origin"][k] + f["d"][k] * f["launch"] for k in range(3)]
        assert math.hypot(f["origin"][0] - BOW_SPOT[0], f["origin"][2] - BOW_SPOT[1]) < 1, (f, BOW_SPOT)
        assert math.hypot(aim[0] - NEAR[0], aim[2] - NEAR[1]) < .5 and 5 < f["launch"] < 7, (aim, NEAR, f)
        # Joint 0 is at the archer's feet and NEAR's box centre above its
        # feet, so the arrow climbs: the direction keeps its pitch (004770c0).
        assert f["d"][1] > .05, (r, f)
        # The release event came after the launch and found the flight in the
        # air (a 6 m flight at 4 m/s takes 1.5 s, so none was held).
        assert r in confirmed and confirmed[r][0] == lands[r] and 0 < confirmed[r][1] < 1 and confirmed[r][2] == 0, \
            (r, confirmed.get(r), lands[r])
    assert not held, held
    assert drawn and {r for r, *_ in drawn} <= set(local), (drawn, local)
    base = [sum(p[k] for p in FLIGHT_TRIANGLE) / 3 for k in range(3)]
    for r, tick, age, anchor, offset, drawn_base in drawn:
        f = local[r]
        assert tick in (0, lands.get(r)), (r, tick, lands.get(r))  # 0: drawn before the release event
        assert all(abs(anchor[k] - (f["origin"][k] + f["d"][k] * f["speed"] * age)) < 1e-3 for k in range(3)), (anchor, f, age)
        assert all(abs(a - b) < 1e-4 for a, b in zip(drawn_base, base)), (drawn_base, base)
        turned = turn_to(f["d"])(base)
        assert all(abs(a - b) < 1e-3 for a, b in zip(offset, turned)), (offset, turned, f["d"])
    assert released <= set(hits), (released, hits, text[-2000:])
    for r, h in hits.items():
        # The ray enters NEAR's box before the box's centre.
        assert h["tick"] == lands[r] and h["target"] == target and h["box"] == 1 and 0 < h["reach"] < local[r]["launch"], (r, h)
        assert h["clip"] == FLIGHT["hit_clip"] and h["joint"] == -1 and -1e-3 <= h["late"] < .2 and h["held"] == 0, (r, h)
    leads = sorted(round(confirmed[r][1], 3) for r in released)
    print(f"PASS graphical client flies each released shot's arrow (PQ-417, PQ-439, PQ-445): {len(released)} flights "
          f"launched by its own client at the predicted release ({predicted:.2f} s after the shot, the drawn clip's marker; "
          f"RANGED_FLIGHT local), {leads} s ahead of the release event that confirmed each (RANGED_FLIGHT confirm, no "
          f"second flight), from the archer's joint 0 toward NEAR's box centre at {FLIGHT['speed']} m/s, climbing "
          f"(direction y {sorted({round(local[r]['d'][1], 3) for r in released})}), drawn at the start plus the direction "
          f"x speed x age and turned from -z to the direction ({len(drawn)} draws), ending where the ray enters NEAR's "
          f"box ({sorted(round(hits[r]['reach'], 2) for r in released)} m of "
          f"{sorted(round(local[r]['launch'], 2) for r in released)}) with the hit clip on NEAR (RANGED_FLIGHT hit)",
          flush=True)


def reconcile_flights(observer, client, sql, delay, without_arrows, target):
    """PQ-445 (D-226): the predicted flight waits for the server's release.
    With every arrow write delayed 0.6 s (the release follows its commit,
    D-224), the bowman shoots NEAR from CLOSE_SPOT: its first arrow, launched
    at the predicted release, reaches NEAR's box before the release event, so
    its hit waits for that event (RANGED_FLIGHT held, then confirm and hit).
    Once the next shot is held (the observer sees the bowman's strike fields
    show a new cast after the first one's 'released') and the first arrow's
    arrival write is done, the test empties the bowman's arrow slot in
    Postgres behind the server's back (its own bag still shows the arrows, so
    that shot was accepted): that shot's release write finds no
    arrow and fails no_ammo with no release event (1298's flying phase fails,
    0046f3f1 returns 4), so its predicted arrow ends and its held hit is
    dropped (RANGED_FLIGHT cancel), and the client, its bag pushed empty,
    shoots no more (RANGED_NO_AMMO)."""
    from world_peer import first
    character = sql("SELECT id FROM characters WHERE name='Bowman'")
    delay(arrows_only=True)
    sql("CREATE TRIGGER delay_wear BEFORE INSERT ON durability_operations FOR EACH ROW EXECUTE FUNCTION delay_wear()")
    phase = {"state": "casting", "emptied": None, "tick": None}

    def during(snap):
        bowman = [v for i, v in snap.items() if first(v, 9) != 1 and i != observer.id]
        result, tick = (first(bowman[0], 14), first(bowman[0], 10)) if bowman else (None, None)
        if phase["state"] == "casting" and result == b"released":
            phase["state"], phase["tick"] = "released", tick
        elif phase["state"] == "released" and result == b"casting" and tick != phase["tick"]:
            # The second cast is held (its release LAND ticks away, then the
            # 0.6 s write); the first arrow's arrival wear write (not
            # delayed) lands within a few ticks of it, so wait that out.
            phase["state"] = "second"
            time.sleep(.3)
            original = bytes.fromhex(sql(f"SELECT encode(state, 'hex') FROM character_bags WHERE character_id={character}"))
            sql(f"UPDATE character_bags SET state=decode('{without_arrows(original).hex()}', 'hex') "
                f"WHERE character_id={character}")
            phase["emptied"] = time.monotonic()

    try:
        text, chosen, seen = client("bowman", 10, during)
    finally:
        sql("DROP TRIGGER delay_wear ON durability_operations; DROP FUNCTION delay_wear()")
    assert phase["emptied"] and chosen == target, (phase, chosen, text[-2000:])
    local, confirmed, held, cancelled, event, drawn, hits = local_flights(text)
    released = {int(r): int(t) for r, t in re.findall(
        r"^RANGED_RELEASED actor=\d+ self=1 request=(\d+) tick=(\d+) hit=0$", text, re.M)}
    shots = sorted(local)
    assert len(shots) == 2 and set(released) == {shots[0]} and not event, (local, released, event, text[-3000:])
    first_, second = shots
    # The first: held at NEAR's box until its delayed release event, then hit.
    assert first_ in held and confirmed.get(first_, (0, 0, 0))[0] == released[first_], (held, confirmed, released)
    tick, lead, was_held = confirmed[first_]
    assert was_held == 1 and lead > .4 and first_ not in cancelled, (confirmed[first_], cancelled)
    h = hits[first_]
    assert h["tick"] == released[first_] and h["target"] == target and h["late"] == 0 and h["held"] > .2, h
    # The second: launched, never released; its flight ended and its hit dropped.
    assert second in cancelled and second not in confirmed and second not in hits, (cancelled, confirmed, hits)
    age, dropped = cancelled[second]
    assert age > .4 and dropped == (1 if second in held else 0), (cancelled[second], held)
    assert re.search(r"^RANGED_NO_AMMO ", text, re.M), text[-2000:]
    print(f"PASS graphical client reconciles its predicted arrow with the server's release (PQ-445): with each arrow "
          f"write delayed 0.6 s, its first shot from {math.dist(CLOSE_SPOT, NEAR):.1f} m flew at its predicted release, "
          f"reached NEAR's box (RANGED_FLIGHT held, reach {held[first_][0]:.2f} m) and its hit waited "
          f"{h['held']:.2f} s for the release event ({lead:.2f} s after the launch, RANGED_FLIGHT confirm), then started "
          f"on NEAR; with its arrows emptied in Postgres the second shot's release failed no_ammo (no release event): "
          f"its predicted arrow ended {age:.2f} s after its launch ({'its held hit dropped' if dropped else 'in the air'}, "
          f"RANGED_FLIGHT cancel) and the client posted the ammo notice (RANGED_NO_AMMO)", flush=True)


def check_flight_clip(package):
    """PQ-417 (D-222): the client refuses a flight naming no effects clip, a
    flight clip with camera-facing (quad) records, which its turn does not
    draw, and a hit naming no clip; the server, which checks the bounds only,
    takes all three."""
    from common import digest, string, u
    import struct
    m = json.loads((package / "recipe.json").read_text())["manifest"]
    files = {p.name: p.read_bytes() for p in package.iterdir() if p.name not in ("release.bin", "release.sha256")}
    key, hit = string(FLIGHT["clip"]), string(FLIGHT["hit_clip"])
    effects, ranged = files["effects.bin"], files["ranged-attack.bin"]
    assert effects.count(key) == 1 and ranged.count(key) == 1 and ranged.count(hit) == 1
    at = effects.index(key) + len(key) + 8
    assert effects[at:at + 4] == u(100)
    quad = u(1) + u(1) + u(0) + u(5) + u(6) + u(199) + u(1) + struct.pack("<11f", 0, 1, 0, 1, 1, 0, 1, 1, 1, 1, -1)
    one_quad = effects[:at] + u(1) + quad + effects[at + 4 + 100 * 136:]
    for name, changed, why in [("a missing clip", {"ranged-attack.bin": ranged.replace(key, string("bow-flighx"))}, "ranged flight missing"),
                               ("a quad clip", {"effects.bin": one_quad}, "ranged flight records"),
                               ("a missing hit", {"ranged-attack.bin": ranged.replace(hit, string("bow-hix"))}, "ranged flight hit missing")]:
        with tempfile.TemporaryDirectory(dir=OUT) as tmp:
            copy = Path(tmp) / "package"
            shutil.copytree(package, copy)
            data = {**files, **changed}
            index = (b"N3R1" + u(1) + u(m["engine_version"]) + u(m["protocol_version"]) + string(m["game_id"])
                     + string(m["package_version"]) + u(len(data)))
            for n, d in sorted(data.items()):
                (copy / n).write_bytes(d)
                index += string(n) + u(len(d)) + digest(d)
            (copy / "release.bin").write_bytes(index)
            got = [subprocess.run(cmd, cwd=ROOT, env={**os.environ, "N3E_PACKAGE": str(copy)}, capture_output=True,
                                  text=True) for cmd in (["build/client/n3e-asset-check", str(copy)],
                                                         ["target/debug/n3e-server", "--check-content"])]
            assert got[0].returncode != 0 and why in got[0].stdout + got[0].stderr, (name, got[0])
            assert got[1].returncode == 0, (name, got[1].stdout[-600:], got[1].stderr[-600:])
    print("PASS the client refuses a flight naming no effects clip, a flight clip with quad records or a hit naming no "
          "clip; the server (bounds only) takes all three", flush=True)


def check_cast_effect_clip(package):
    """PQ-423 (D-220): the client refuses a cast effect that names no clip of
    the package's effects or a clip with camera-facing (quad) records, whose
    turn in a self FX n3e does not draw; the server, which checks the bounds
    only, takes both."""
    from common import digest, string, u
    import struct
    m = json.loads((package / "recipe.json").read_text())["manifest"]
    files = {p.name: p.read_bytes() for p in package.iterdir() if p.name not in ("release.bin", "release.sha256")}
    key = string(CAST_EFFECT["clip"])
    effects, ranged = files["effects.bin"], files["ranged-attack.bin"]
    assert effects.count(key) == 1 and ranged.count(key) == 1
    # The clip: its key, scaled and rate, then 30 frames of one 3-record triangle batch (136 bytes each).
    at = effects.index(key) + len(key) + 8
    assert effects[at:at + 4] == u(30)
    quad = u(1) + u(1) + u(0) + u(5) + u(6) + u(199) + u(1) + struct.pack("<11f", 0, 1, 0, 1, 1, 0, 1, 1, 1, 1, -1)
    one_quad = effects[:at] + u(1) + quad + effects[at + 4 + 30 * 136:]
    renamed = ranged.replace(key, string("bow-cass"))
    for name, changed in [("a missing clip", {"ranged-attack.bin": renamed}), ("a quad clip", {"effects.bin": one_quad})]:
        with tempfile.TemporaryDirectory(dir=OUT) as tmp:
            copy = Path(tmp) / "package"
            shutil.copytree(package, copy)
            data = {**files, **changed}
            index = (b"N3R1" + u(1) + u(m["engine_version"]) + u(m["protocol_version"]) + string(m["game_id"])
                     + string(m["package_version"]) + u(len(data)))
            for n, d in sorted(data.items()):
                (copy / n).write_bytes(d)
                index += string(n) + u(len(d)) + digest(d)
            (copy / "release.bin").write_bytes(index)
            got = [subprocess.run(cmd, cwd=ROOT, env={**os.environ, "N3E_PACKAGE": str(copy)}, capture_output=True,
                                  text=True) for cmd in (["build/client/n3e-asset-check", str(copy)],
                                                         ["target/debug/n3e-server", "--check-content"])]
            assert got[0].returncode != 0 and "ranged cast effect" in got[0].stdout + got[0].stderr, (name, got[0])
            assert got[1].returncode == 0, (name, got[1].stdout[-600:], got[1].stderr[-600:])
    print("PASS the client refuses a cast effect naming no effects clip or a clip with quad records; the server "
          "(bounds only) takes both", flush=True)


def check_readers(package):
    """Both readers accept the package and bind the same release identity."""
    results = []
    for cmd in [["build/client/n3e-asset-check", str(package)], ["target/debug/n3e-server", "--check-content"]]:
        p = subprocess.run(cmd, cwd=ROOT, env={**os.environ, "N3E_PACKAGE": str(package)}, capture_output=True,
                           text=True)
        assert p.returncode == 0, (cmd, p.stdout[-600:], p.stderr[-600:])
        results.append(p.stdout.splitlines())
    assert set(results[0]) & set(results[1]), "readers disagree on the release"


def live(package):
    from isolation import DISPOSABLE_POSTGRES, container_logs, free_ports
    from readiness import wait_postgres
    from world_peer import Peer, blob, fields, first, integer
    import urllib.request

    manifest = json.loads((package / "recipe.json").read_text())["manifest"]
    out = OUT / "live"
    out.mkdir(parents=True, exist_ok=True)
    server_binary = str(Path(os.environ.get("N3E_TEST_SERVER", "target/debug/n3e-server")).resolve())
    name = "n3e-pq416-" + uuid.uuid4().hex[:10]
    passwords = {account: "test-only-" + uuid.uuid4().hex for account in ("archer", "scout", "bowman", "warden")}
    containers, server, log = [], None, None

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
        p.send(32, integer(1, op) + blob(2, f"pq416-{serial[0]}") + integer(3, first(state, 1)) + integer(4, source)
               + integer(5, destination) + integer(6, first(fields(records[source]), 1)))
        d = wait(p, 33)
        assert first(d, 2) == status, (status, d)
        return fields(first(d, 3))

    def arrows(p):
        """The arrows in the first bag slot holding them (0: none), from the
        server's durable bag."""
        found = [first(fields(r), 3) for r in bag(p)[5] if first(fields(r), 2) == ARROW.encode()]
        return found[0] if found else 0

    def slot_of(state, item):
        found = [i for i, r in enumerate(state[5]) if first(fields(r), 2) == item.encode()]
        assert found, (item, state)
        return found[0]

    def without_arrows(state):
        """PQ-444: an encoded BagState with its arrow slot (field 5) emptied,
        as the server leaves an emptied slot (an empty ItemStack), and every
        other field byte for byte, the revision unchanged."""
        out, p, emptied = b"", 0, 0

        def vint():
            nonlocal p
            n, shift = 0, 0
            while True:
                x = state[p]
                p += 1
                n |= (x & 127) << shift
                shift += 7
                if x < 128:
                    return n
        while p < len(state):
            at = p
            key = vint()
            if key & 7 == 0:
                vint()
            elif key & 7 == 2:
                n = vint()
                p += n
                if key >> 3 == 5 and first(fields(state[p - n:p]), 2) == ARROW.encode():
                    out, emptied = out + blob(5, b""), emptied + 1
                    continue
            elif key & 7 == 5:
                p += 4
            elif key & 7 == 1:
                p += 8
            else:
                raise ValueError("wire kind")
            out += state[at:p]
        assert emptied == 1, emptied
        return out

    def walk(p, x, z):
        end = time.monotonic() + 30
        while time.monotonic() < end:
            p.pump(.05)
            me = p.entities[p.id]
            if first(me, 6) < p.seq:
                continue
            dx, dz = x - first(me, 3), z - first(me, 5)
            d = math.hypot(dx, dz)
            if d < .05:
                p.move(0, 0)
                p.pump(.3)
                return
            step = min(1, d / .08)  # walk speed 1.5 m/s: 0.075 m a tick
            p.move(dx / d * step, dz / d * step)
        raise AssertionError(("blocked", x, z, p.entities[p.id]))

    def attack_now(p):
        """PQ-422: the archer's derived attack in the next World message
        (owner-only field 13, DerivedStats attack 1)."""
        return first(fields(first(wait(p, 10, lambda d: 13 in d), 13)), 1)

    def npc(p, template):
        found = [e for e in p.entities.values() if first(e, 9) == 1 and first(e, 2) == template.encode()]
        assert len(found) == 1, (template, [first(e, 2) for e in p.entities.values()])
        return found[0]

    def position(e):
        return first(e, 3), first(e, 4), first(e, 5)

    def send_shot(p, target):
        """An attack request that does not wait for its result (PQ-420)."""
        p.action_seq += 1
        p.send(15, integer(1, p.session) + integer(2, p.action_seq) + integer(3, target) + blob(4, p.action_id))
        return p.action_seq

    def settle(p, seconds, snaps, events):
        """Gather world snapshots (tick, entities) and events (by sequence)."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            record(p, *p.receive(), snaps, events)

    # PQ-439: the derived attacks the archer's World messages carry (owner-only
    # field 13), for a shot whose arrow lands after an earlier one's wear.
    seen_attacks = []
    # PQ-444: every message the archer's records take is numbered; the bag
    # states the server pushes unasked (request '': a durable wear or arrow
    # write) are kept as (number, status, arrows), and each event's first
    # number, so a push can be ordered against the events.
    received, pushes, heard, worlds = [0], [], {}, []

    def record(p, t, d, snaps, events):
        assert t != 4, (t, d)
        received[0] += 1
        if t == 33 and not first(d, 1):
            held = [first(fields(r), 3) for r in fields(first(d, 3, b"")).get(5, []) if first(fields(r), 2) == ARROW.encode()]
            pushes.append((received[0], first(d, 2), held[0] if held else 0))
        if t == 10:
            worlds.append((received[0], first(d, 1)))
            if 13 in d:
                seen_attacks.append(first(fields(first(d, 13)), 1))
            snaps.append((first(d, 1), {i: dict(e) for i, e in p.entities.items()}))
            for raw in d.get(14, []):
                ev = fields(raw)
                events[first(ev, 1)] = ev
                heard.setdefault(first(ev, 1), received[0])

    def collect(p, seq, seconds=6):
        """Snapshots and events until `seq`'s result: (status, damage, snaps, events)."""
        snaps, events = [], {}
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            t, d = p.receive()
            record(p, t, d, snaps, events)
            if t == 16 and first(d, 1) == seq:
                return first(d, 2, b"").decode(), first(d, 4), snaps, events
        raise AssertionError(("no result", seq))

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
            p.pump(.5)
            return p

        a = peer("archer")
        me = a.entities[a.id]
        near, far = npc(a, TEMPLATES[0]["name"]), npc(a, TEMPLATES[1]["name"])
        d_near, d_far = math.dist(position(me), position(near)), math.dist(position(me), position(far))
        assert abs(d_near - 6) < .3 and abs(d_far - 15) < .3, (d_near, d_far, position(me))
        # 1. The melee profile (unarmed, style 1) refuses NEAR at 6 m: melee
        # reach is half the radii, 1 m.
        assert first(me, 22) == 1, me
        assert a.action(first(near, 1)) == "out_of_range"
        # 2. The blade worn in the right hand selects profile 2, the ranged one.
        state = bag(a)
        state = bag(a, 5, slot_of(state, BLADE), 0, state)
        wait(a, 10, lambda _: first(a.entities[a.id], 22) == 2)
        a.pump(PAUSE)  # past the interval of the refused try
        start = position(a.entities[a.id])
        assert arrows(a) == ARROWS
        spent = 0  # the shots that landed (PQ-421: one arrow each)
        # 3. FAR, 15 m away, is beyond the 10 m limit.
        assert a.action(first(far, 1)) == "out_of_range"
        # 4. NEAR, 6 m away: accepted where the archer stands and held for
        # its cast (PQ-420): the strike fields show it from the acceptance,
        # the target is unharmed until the shot lands. PQ-439 (D-223): at the
        # landing tick, LAND ticks later, the server releases it (a kind-7
        # event, strike_result 'released'); it lands when its arrow arrives,
        # the 3-D distance over the flight's speed later, as a kind-6 event,
        # and the result arrives then.
        near_id = first(near, 1)
        hp0 = first(npc(a, TEMPLATES[0]["name"]), 7)
        attack = attack_now(a)
        sent = time.monotonic()
        seq = send_shot(a, near_id)
        snaps, events = [], {}
        end = time.monotonic() + 3
        while not any(first(e[a.id], 30) == seq and first(e[a.id], 14) == b"released" for _, e in snaps):
            assert time.monotonic() < end, "the shot was never released"
            record(a, *a.receive(), snaps, events)
        # 5. Released, its arrow in flight, inside the interval (2000 ms, 40
        # ticks from the cast start), the next try is cooldown, not refused
        # for the arrow.
        early = send_shot(a, near_id)
        refused, _, more, more_events = collect(a, early)
        snaps += more
        events.update(more_events)
        assert refused == "cooldown", refused
        # Once the interval has run, with the first arrow (30 ticks at 6 m)
        # still in the air, a second shot is accepted and held (1298's bow
        # tick casts once an interval, 004659b0; neither it nor 005819e0
        # tests the flight: binary, by absence, PQ-439 evidence).
        while time.monotonic() < sent + PAUSE:
            record(a, *a.receive(), snaps, events)
        overlap = send_shot(a, near_id)
        mark = len(seen_attacks)
        result, damage, more, more_events = collect(a, seq)
        snaps += more
        events.update(more_events)
        assert result in ("hit", "miss"), result
        spent += 1
        # PQ-422: every landed shot's result and damage, with the archer's
        # derived attack when it was sent (the blade wears).
        shots = [(result, damage, attack)]
        result2, damage2, more, more_events = collect(a, overlap, seconds=8)
        snaps += more
        events.update(more_events)
        assert result2 in ("hit", "miss"), result2
        spent += 1
        # The first arrow's landing wore the blade before this one arrived.
        shots.append((result2, damage2, (attack, *seen_attacks[mark:])))
        settle(a, .4, snaps, events)
        of = lambda s, kind: [e for e in events.values() if first(e, 5) == kind and first(e, 17) == s]  # noqa: E731
        cast = sorted(first(e[a.id], 10) for _, e in snaps if first(e[a.id], 30) == seq)
        assert cast and cast[0] == cast[-1], cast
        started = cast[0]
        starts, releases, lands = of(seq, 2), of(seq, 7), of(seq, 6)
        assert len(starts) == 1 and len(releases) == 1 and len(lands) == 1, events
        released = first(releases[0], 2)
        landed = first(lands[0], 2)
        fly = flight_ticks(releases[0])
        assert released - started == LAND, (started, released)
        assert 25 <= fly <= 35, (fly, releases[0])  # 6 m at 4 m/s: 30
        # The strike lands when its arrow arrives, once its durable wear
        # write has committed (PQ-444: a tick after the arrival; the arrow
        # went at the release), later only when the database is slow.
        assert fly <= landed - released <= fly + 20, (released, landed, fly)
        # A snapshot of tick T is built before that tick's commands: the cast
        # shows from T + 1, the landing (resolved in tick L's commands) from L + 1.
        o_starts, o_releases, o_lands = of(overlap, 2), of(overlap, 7), of(overlap, 6)
        assert len(o_starts) == 1 and len(o_releases) == 1 and len(o_lands) == 1, events
        o_started, o_released, o_landed = (first(o_starts[0], 2), first(o_releases[0], 2), first(o_lands[0], 2))
        held = [(t, e) for t, e in snaps if started < t < released]
        flying = [(t, e) for t, e in snaps if released < t <= landed]
        between = [(t, e) for t, e in snaps if landed < t <= o_landed]
        after = [(t, e) for t, e in snaps if t > o_landed]
        assert held and flying and between and after, ([t for t, _ in snaps], started, released, landed, o_landed)
        assert all(first(e[a.id], 14) == b"casting" and first(e[a.id], 15) == 0 and first(e[near_id], 7) == hp0
                   for _, e in held), [(t, first(e[a.id], 14), first(e[near_id], 7)) for t, e in held]
        assert all(first(e[near_id], 7) == hp0 for _, e in flying), [(t, first(e[near_id], 7)) for t, e in flying]
        assert all((first(e[a.id], 14), first(e[a.id], 10), first(e[a.id], 30)) == (b"released", started, seq)
                   for t, e in flying if t < o_started), [(t, first(e[a.id], 14)) for t, e in flying]
        assert all(first(e[near_id], 7) == hp0 - damage for _, e in between), [first(e[near_id], 7) for _, e in between]
        assert all(first(e[a.id], 14) == result2.encode() and first(e[a.id], 10) == o_started
                   and first(e[near_id], 7) == hp0 - damage - damage2 for _, e in after), \
            [(t, first(e[a.id], 14), first(e[a.id], 10), first(e[near_id], 7)) for t, e in after]
        assert first(starts[0], 2) == started and not first(starts[0], 9), starts
        assert bool(first(lands[0], 9)) == (result == "hit"), lands
        assert first(lands[0], 3) == a.id and first(lands[0], 4) == near_id, lands
        assert (first(releases[0], 3), first(releases[0], 4), first(releases[0], 7)) == (a.id, near_id, 2), releases
        assert not first(releases[0], 9), releases
        # PQ-444 (D-224): the release spent the arrow in its own durable
        # write: the server pushed the bag with one arrow fewer after the cast
        # start and before any snapshot two ticks past the release, long
        # before the arrival (before PQ-444 that push came with the arrival's
        # commit, 30 ticks later).
        spend = [n for n, status, held_ in pushes if held_ == ARROWS - 1 and status == b"worn"]
        later = [n for n, t in worlds if t >= released + 2]
        assert spend and later and heard[first(starts[0], 1)] < spend[0] < later[0], (pushes, released, worlds[-5:])
        # The overlapping shot: accepted after the interval, before the first
        # arrow landed; that landing left its cast's strike fields alone (no
        # second start event, 'casting' from its start to its release) and
        # carried the first shot's own request sequence and style.
        assert started + 40 <= o_started < landed < o_released, (started, o_started, landed, o_released)
        assert o_released - o_started == LAND, (o_started, o_released)
        assert first(lands[0], 7) == 2 and first(o_lands[0], 7) == 2, (lands, o_lands)
        assert first(o_lands[0], 2) - o_released >= flight_ticks(o_releases[0]), (o_released, o_lands)
        o_held = [(t, e) for t, e in snaps if o_started < t < o_released]
        assert any(t > landed for t, _ in o_held), ([t for t, _ in o_held], landed)
        assert all((first(e[a.id], 10), first(e[a.id], 30), first(e[a.id], 14)) == (o_started, overlap, b"casting")
                   for _, e in o_held), [(t, first(e[a.id], 10), first(e[a.id], 30), first(e[a.id], 14)) for t, e in o_held]
        me = a.entities[a.id]
        assert (first(me, 25), first(me, 23), first(me, 24) or 0) == (near_id, 2, 0), me
        assert math.dist(position(me), start) < 1e-4, (position(me), start)
        assert math.dist(position(me), position(npc(a, TEMPLATES[0]["name"]))) > 5.5
        print(f"PASS the server holds the shot for its cast (PQ-420) and lands it when its arrow arrives (PQ-439): "
              f"accepted at tick {started}, the strike fields show the cast ('casting', NEAR unharmed) for "
              f"{len(held)} snapshots, released at tick {released} ({LAND} ticks: the stretched clip's marker, blend "
              f"0.2 + 0.8 x 0.9 s) as a kind-7 event ('released', NEAR still unharmed for {len(flying)} snapshots), "
              f"landed at tick {landed} ({landed - released} ticks later: {fly} for its "
              f"{math.dist(position(me), position(npc(a, TEMPLATES[0]['name']))):.2f} m at {FLIGHT['speed']} m/s, its "
              f"wear commit after it; its arrow went at the release, the bag pushed with {ARROWS - 1} before tick "
              f"{released + 2}, PQ-444) as a kind-6 event ({result}, {damage} damage), the result "
              f"came then; the next try inside the interval was cooldown, and one after it, at tick {o_started}, was "
              f"held while the first arrow flew, its cast untouched by that landing", flush=True)
        # 6. A second shot while one is held is refused; the first still lands.
        a.pump(PAUSE)
        attack = attack_now(a)
        first_seq = send_shot(a, near_id)
        second_seq = send_shot(a, near_id)
        assert collect(a, second_seq)[0] == "combat_pending"
        shots.append((*collect(a, first_seq)[:2], attack))
        assert shots[-1][0] in ("hit", "miss")
        spent += 1
        assert arrows(a) == ARROWS - spent, (arrows(a), spent)
        # 7. A movement input after the acceptance cancels the shot: no damage,
        # no landing, and the cast leaves the strike fields.
        a.pump(PAUSE)
        hp1 = first(npc(a, TEMPLATES[0]["name"]), 7)
        seq = send_shot(a, near_id)
        snaps, events = [], {}
        settle(a, .3, snaps, events)
        assert any(first(e[a.id], 30) == seq for _, e in snaps), "the cast never showed"
        a.move(1, 0)
        result, damage, more, events = collect(a, seq)
        a.move(0, 0)
        assert (result, damage) == ("interrupted", 0), (result, damage)
        settle(a, 1.2, more, events)
        assert not [e for e in events.values() if first(e, 5) in (6, 7) and first(e, 17) == seq], events
        assert all(first(e[near_id], 7) == hp1 for _, e in more), [first(e[near_id], 7) for _, e in more]
        me = a.entities[a.id]
        assert (first(me, 10), first(me, 30)) == (0, 0), me
        assert arrows(a) == ARROWS - spent, "a cancelled shot spends no arrow"
        print(f"PASS a movement after the acceptance cancels the held shot (1298 00585830 on a walk): result "
              f"'interrupted' before the landing, NEAR unharmed ({hp1}), no release or landing event, the cast cleared "
              f"from the strike fields; a second shot while one was held was refused as combat_pending", flush=True)
        # 7b. PQ-439 (D-223): once released, a movement cancels nothing: the
        # arrow flies on (1298's FX tick 0047a8d0 reports it wherever the
        # shooter goes) and lands at its arrival.
        a.pump(PAUSE)
        hp2 = first(npc(a, TEMPLATES[0]["name"]), 7)
        attack = attack_now(a)
        seq = send_shot(a, near_id)
        snaps, events = [], {}
        end = time.monotonic() + 3
        while not any(first(e[a.id], 30) == seq and first(e[a.id], 14) == b"released" for _, e in snaps):
            assert time.monotonic() < end, "the shot was never released"
            record(a, *a.receive(), snaps, events)
        here = position(a.entities[a.id])
        a.move(1, 0)
        result, damage, more, events = collect(a, seq, seconds=8)
        a.move(0, 0)
        assert result in ("hit", "miss") and damage > 0, (result, damage)
        spent += 1
        shots.append((result, damage, attack))
        settle(a, .4, more, events)
        lands = [e for e in events.values() if first(e, 5) == 6 and first(e, 17) == seq]
        assert len(lands) == 1, events
        stepped = [t for t, e in more if t <= first(lands[0], 2) and math.dist(position(e[a.id]), here) > .01]
        assert stepped, [(t, position(e[a.id])) for t, e in more]
        assert first(npc(a, TEMPLATES[0]["name"]), 7) == hp2 - damage
        print(f"PASS a movement after the release does not cancel the shot (PQ-439): the archer stepped "
              f"{math.dist(position(a.entities[a.id]), here):.2f} m while its arrow flew, and the shot landed "
              f"({result}, {damage} damage)", flush=True)
        # 7c. PQ-444 (D-224): the arrow is spent at the release, so a shot
        # cancelled in flight has spent it (1298's flying phase 0046f3f1 took
        # it whatever the arrow then did). The archer takes the blade off
        # while its arrow flies: the shot is cancelled (equipment_changed),
        # NEAR unharmed, the arrow gone; then it wears the blade again.
        a.pump(PAUSE)
        quiver = arrows(a)
        hp3 = first(npc(a, TEMPLATES[0]["name"]), 7)
        seq = send_shot(a, near_id)
        snaps, events = [], {}
        end = time.monotonic() + 3
        while not any(first(e[a.id], 30) == seq and first(e[a.id], 14) == b"released" for _, e in snaps):
            assert time.monotonic() < end, "the shot was never released"
            record(a, *a.receive(), snaps, events)
        state = bag(a)  # the bag after the release's write
        free = next(i for i, r in enumerate(state[5]) if not first(fields(r), 1))
        serial[0] += 1
        off = f"pq444-{serial[0]}"
        a.send(32, integer(1, 6) + blob(2, off) + integer(3, first(state, 1)) + integer(4, 0) + integer(5, free)
               + integer(6, first(fields(state[6][0]), 1)))
        result, unequipped, end = None, False, time.monotonic() + 6
        while result is None or not unequipped:
            assert time.monotonic() < end, (result, unequipped)
            t, d = a.receive()
            record(a, t, d, snaps, events)
            if t == 33 and first(d, 1) == off.encode():
                assert first(d, 2) == b"committed", d
                unequipped = True
            if t == 16 and first(d, 1) == seq:
                result, damage = first(d, 2, b"").decode(), first(d, 4)
        assert (result, damage) == ("equipment_changed", 0), (result, damage)
        settle(a, .5, snaps, events)
        assert not [e for e in events.values() if first(e, 5) == 6 and first(e, 17) == seq], events
        assert first(npc(a, TEMPLATES[0]["name"]), 7) == hp3
        spent += 1
        assert arrows(a) == quiver - 1 == ARROWS - spent, (arrows(a), quiver, spent)
        state = bag(a)
        bag(a, 5, slot_of(state, BLADE), 0, state)
        wait(a, 10, lambda _: first(a.entities[a.id], 22) == 2)
        print(f"PASS a shot cancelled in flight has spent its arrow (PQ-444, 1298 0046f3f1 at the flying phase): "
              f"released, then the blade taken off while its arrow flew: '{result}', NEAR unharmed ({hp3}), "
              f"{quiver} -> {quiver - 1} arrows", flush=True)
        # 8. A movement queued beside the shot does not make it a moving strike
        # and does not cancel it (it was admitted before the acceptance).
        walk(a, *start[::2])
        a.pump(PAUSE)
        a.move(1, 0)
        result = a.action(first(npc(a, TEMPLATES[0]["name"]), 1))
        assert result in ("hit", "miss"), result
        spent += 1
        a.move(0, 0)
        a.pump(.4)
        me = a.entities[a.id]
        assert first(me, 23) == 2 and not first(me, 24), me
        print(f"PASS the server checks the ranged profile from committed equipment: unarmed (melee) refuses NEAR at "
              f"{d_near:.2f} m, with the blade (style 2) FAR at {d_far:.2f} m is out of range and NEAR is struck "
              f"without the archer moving, never as a moving strike (also with a movement queued), the next try "
              f"inside the interval is cooldown", flush=True)
        # 8b. PQ-447 (D-227): once a shot is released, a skill or rest starts
        # while its arrow flies (20 ticks at 4 m), as in 1298: its skill start
        # (005819e0) and sit command (005d91f0) test the cast, not the arrow,
        # and Ebenezer neither ties a new cast nor sitting to it (004630a6,
        # 004a8ad1). The arrow lands during the heal's cast and under the
        # sitting archer, who stays seated (Ebenezer's effecting phase does not
        # test the posture and writes none). Before PQ-447 both were refused
        # (combat_pending, rest_unavailable) until the arrow landed.
        def released(seq):
            snaps, events = [], {}
            end = time.monotonic() + 3
            while not any(first(e[a.id], 30) == seq and first(e[a.id], 14) == b"released" for _, e in snaps):
                assert time.monotonic() < end, "the shot was never released"
                record(a, *a.receive(), snaps, events)
            return snaps, events

        def landing(seq, events):
            lands = [e for e in events.values() if first(e, 5) == 6 and first(e, 17) == seq]
            releases = [e for e in events.values() if first(e, 5) == 7 and first(e, 17) == seq]
            assert len(lands) == 1 and len(releases) == 1, sorted((first(e, 17), first(e, 5)) for e in events.values())
            return first(releases[0], 2), first(lands[0], 2)

        # From 4 m the arrow (20 ticks) lands well inside the heal's 30-tick
        # cast that starts a few ticks after the release, with margin on both
        # sides for a slow heal start or a slow arrival write.
        target = position(npc(a, TEMPLATES[0]["name"]))
        walk(a, target[0], target[2] + 4)
        a.pump(PAUSE)
        near_id = first(npc(a, TEMPLATES[0]["name"]), 1)
        hp6 = first(npc(a, TEMPLATES[0]["name"]), 7)
        attack = attack_now(a)
        seq = send_shot(a, near_id)
        snaps, events = released(seq)
        a.action_seq += 1
        heal = a.action_seq
        a.send(15, integer(1, a.session) + integer(2, heal) + integer(3, a.id) + blob(4, HEAL))
        replies = []
        end = time.monotonic() + 8
        def done(r_):
            return any(r == r_ and s_ not in ("cast_pending", "casting") for r, s_ in replies)
        while not (done(heal) and done(seq)):
            assert time.monotonic() < end, replies
            t, d = a.receive()
            record(a, t, d, snaps, events)
            if t == 16 and first(d, 1) in (seq, heal):
                replies.append((first(d, 1), first(d, 2, b"").decode()))
                if first(d, 1) == seq:
                    damage = first(d, 4)
        settle(a, .3, snaps, events)
        mine = [s_ for r, s_ in replies if r == heal]
        assert mine[:2] == ["cast_pending", "casting"] and mine[-1] == "healed", replies
        result = next(s_ for r, s_ in replies if r == seq)
        assert result in ("hit", "miss") and damage > 0, replies
        spent += 1
        shots.append((result, damage, attack))
        let_go, landed = landing(seq, events)
        # PQ-454 (D-228): the release paid the basic attack's cost (the
        # arrow's write starts at the release tick), and the arrival took
        # none: before PQ-454 the arrival took it, after the release. Nothing
        # else spends resource here (the heal pays at its impact, after
        # cast_to); regeneration adds at most 1 on each REGEN-th tick.
        mana = [(t, first(e[a.id], 8)) for t, e in snaps]
        t0, r0 = mana[0]
        t1, r1 = next(m_ for m_ in mana if m_[0] >= let_go)
        regen = sum(1 for t in range(t0 + 1, t1 + 1) if t % REGEN == 0)
        assert t0 < let_go and r0 - COST <= r1 <= r0 - COST + regen, (let_go, mana)
        before = [m_ for m_ in mana if m_[0] < landed][-1]
        after = next(m_ for m_ in mana if m_[0] >= landed)
        assert after[1] >= before[1], (landed, before, after, mana)
        cast = sorted({(first(e[a.id], 27), first(e[a.id], 28)) for _, e in snaps if first(e[a.id], 26) == HEAL.encode()})
        assert len(cast) == 1 and cast[0][1] - cast[0][0] == 30, cast
        (cast_from, cast_to), = cast
        # The heal started while the arrow flew, and the arrow landed before
        # the cast ended (the heal resolves only after cast_to).
        assert let_go < cast_from < landed < cast_to, (let_go, cast_from, landed, cast_to)
        assert 15 <= landed - let_go <= 40, (let_go, landed)  # 4 m at 4 m/s: 20, its wear commit after it
        assert first(npc(a, TEMPLATES[0]["name"]), 7) == hp6 - damage
        print(f"PASS a skill starts while the archer's arrow flies (PQ-447, 1298 005819e0 tests the cast, not the "
              f"arrow): released at tick {let_go}, the heal accepted ('cast_pending') and cast from tick {cast_from}, "
              f"the arrow landed at tick {landed} ({result}, {damage} damage), inside the cast (to tick {cast_to}), "
              f"the heal then 'healed'", flush=True)
        print(f"PASS the release pays the basic attack's cost (PQ-454, Ebenezer 0046f3f1 -> 004a083f): resource "
              f"{r0} at tick {t0}, {r1} at tick {t1} after the release at {let_go} (cost {COST}, {regen} regenerated), "
              f"{before[1]} -> {after[1]} across the arrival at tick {landed}", flush=True)
        a.pump(PAUSE)
        hp7 = first(npc(a, TEMPLATES[0]["name"]), 7)
        attack = attack_now(a)
        seq = send_shot(a, near_id)
        snaps, events = released(seq)
        a.send(45, integer(1, a.session) + integer(2, 1) + integer(3, a.id) + integer(4, 1))
        result, damage, more, more_events = collect(a, seq, seconds=8)
        snaps += more
        events.update(more_events)
        settle(a, .3, snaps, events)
        assert result in ("hit", "miss") and damage > 0, (result, damage)
        spent += 1
        shots.append((result, damage, attack))
        let_go, landed = landing(seq, events)
        seated = [t for t, e in snaps if first(e[a.id], 21)]
        assert seated and let_go < seated[0] < landed, (seated, let_go, landed)
        assert all(first(e[a.id], 21) for t, e in snaps if t >= seated[0]), [(t, first(e[a.id], 21)) for t, e in snaps]
        assert any(t > landed for t, _ in snaps), ([t for t, _ in snaps], landed)
        assert first(npc(a, TEMPLATES[0]["name"]), 7) == hp7 - damage
        a.send(45, integer(1, a.session) + integer(2, 2) + integer(3, a.id) + integer(4, 0))
        wait(a, 10, lambda _: not first(a.entities[a.id], 21))
        print(f"PASS the archer sits while its arrow flies (PQ-447, Ebenezer 004a8ad1 does not test it): released at "
              f"tick {let_go}, seated from tick {seated[0]}, the arrow landed at tick {landed} ({result}, {damage} "
              f"damage) with the archer still seated ({len([t for t in seated if t > landed])} snapshots after it)",
              flush=True)
        # 7. The limit is both radii plus the range, 10 m, in 3-D. (A healed
        # NPC takes a fresh entity id, gameplay.rs, so each strike names the
        # current one.)
        target = position(npc(a, TEMPLATES[0]["name"]))
        walk(a, target[0], target[2] + LIMIT - .5)
        a.pump(PAUSE)
        inside = math.dist(position(a.entities[a.id]), target)
        assert LIMIT - .7 < inside < LIMIT - .3, inside
        # PQ-439 (D-223): its arrow flies about 48 ticks, longer than the
        # interval less the cast, so a second shot sent once the interval has
        # run reaches its release with the first still in the air: that
        # release waits until the first lands.
        target_id = first(npc(a, TEMPLATES[0]["name"]), 1)
        attack = attack_now(a)
        sent = time.monotonic()
        s1 = send_shot(a, target_id)
        snaps, events = [], {}
        while time.monotonic() < sent + PAUSE:
            record(a, *a.receive(), snaps, events)
        s2 = send_shot(a, target_id)
        mark = len(seen_attacks)
        for s_, seconds in ((s1, 8), (s2, 10)):
            result, damage, more, more_events = collect(a, s_, seconds=seconds)
            snaps += more
            events.update(more_events)
            assert result in ("hit", "miss"), (result, inside)
            spent += 1
            shots.append((result, damage, attack if s_ == s1 else (attack, *seen_attacks[mark:])))
        settle(a, .3, snaps, events)
        tick_of = {(first(e, 17), first(e, 5)): first(e, 2) for e in events.values()}
        release1 = [e for e in events.values() if (first(e, 17), first(e, 5)) == (s1, 7)]
        assert len(release1) == 1 and all((s_, k) in tick_of for s_ in (s1, s2) for k in (2, 6, 7)), tick_of
        fly1 = flight_ticks(release1[0])
        assert 45 <= fly1 <= 50, fly1  # 9.5 m at 4 m/s: 48
        due = tick_of[s2, 2] + LAND
        assert tick_of[s2, 2] < due < tick_of[s1, 7] + fly1 - 1, (tick_of, fly1)
        assert tick_of[s1, 7] + fly1 - 1 <= tick_of[s2, 7] <= tick_of[s1, 6] + 1, (tick_of, fly1)
        assert tick_of[s2, 6] - tick_of[s2, 7] >= flight_ticks(
            [e for e in events.values() if (first(e, 17), first(e, 5)) == (s2, 7)][0]), tick_of
        print(f"PASS a release waits for the archer's previous arrow (PQ-439): at {inside:.2f} m the first arrow flew "
              f"{fly1} ticks, the second shot (accepted at tick {tick_of[s2, 2]}, due at {due}) was released at tick "
              f"{tick_of[s2, 7]}, when the first landed ({tick_of[s1, 6]}), and both landed", flush=True)
        # PQ-467 (D-233): the hold is checked again when the arrow arrives,
        # from where the archer stands then, as Ebenezer's effecting phase
        # passes 004c1dbe (004635c8) with both sides' current positions. An
        # archer that walks away after the release (which no longer cancels
        # the shot, PQ-439) takes NEAR out of the 10.5 m hold before its arrow
        # (48 ticks at 9.5 m) lands: the shot fails out_of_range at its
        # arrival, NEAR unharmed and no landing event, its arrow and cost
        # already spent at the release (D-224, D-228).
        a.pump(PAUSE)
        quiver = arrows(a)
        hp_hold = first(npc(a, TEMPLATES[0]["name"]), 7)
        target_id = first(npc(a, TEMPLATES[0]["name"]), 1)
        away = send_shot(a, target_id)
        snaps, events = released(away)
        # One movement input is one tick's step, so walk (+z, away from NEAR)
        # with an input every 50 ms until the result.
        result, stepped, deadline = None, 0., time.monotonic() + 8
        while result is None:
            assert time.monotonic() < deadline, "no result for the shot"
            if time.monotonic() - stepped >= .05:
                a.move(0, 1)
                stepped = time.monotonic()
            t, d = a.receive()
            record(a, t, d, snaps, events)
            if t == 16 and first(d, 1) == away:
                result, damage = first(d, 2, b"").decode(), first(d, 4)
        a.move(0, 0)
        assert (result, damage) == ("out_of_range", 0), (result, damage)
        settle(a, .4, snaps, events)
        mine = [e for e in events.values() if first(e, 17) == away]
        assert sorted(first(e, 5) for e in mine) == [2, 7], sorted((first(e, 17), first(e, 5)) for e in events.values())
        let_go = first([e for e in mine if first(e, 5) == 7][0], 2)
        flown = flight_ticks([e for e in mine if first(e, 5) == 7][0])
        assert 45 <= flown <= 50, flown
        ground = lambda e: math.hypot(first(e, 3) - target[0], first(e, 5) - target[2])  # noqa: E731
        # The archer walks away monotonically, so its last snapshot at or
        # before the arrival tick bounds its distance there from below.
        before = [(t, ground(e[a.id])) for t, e in snaps if t <= let_go + flown]
        assert before and before[-1][1] > HOLD["distance"] + .3, (before[-3:], let_go, flown)
        at_arrival = [before[-1][1]]
        assert all(first(e[target_id], 7) == hp_hold for _, e in snaps if target_id in e), "NEAR was hurt"
        assert first(npc(a, TEMPLATES[0]["name"]), 7) == hp_hold
        spent += 1
        assert arrows(a) == quiver - 1 == ARROWS - spent, (arrows(a), quiver, spent)
        print(f"PASS the hold is checked again at the arrival (PQ-467, Ebenezer 004c1dbe on the effecting phase): "
              f"released at {inside:.2f} m, the archer walked away while its arrow flew {flown} ticks and stood "
              f"{at_arrival[0]:.2f} m from NEAR on the ground plane at its arrival, beyond the {HOLD['distance']} m "
              f"hold: '{result}', no landing event, NEAR unharmed ({hp_hold}), the arrow spent at the release "
              f"({quiver} -> {quiver - 1})", flush=True)
        walk(a, target[0], target[2] + LIMIT + .5)
        a.pump(PAUSE)
        beyond = math.dist(position(a.entities[a.id]), target)
        assert LIMIT + .3 < beyond < LIMIT + .7, beyond
        assert a.action(first(npc(a, TEMPLATES[0]["name"]), 1)) == "out_of_range", beyond
        print(f"PASS the ranged limit is the radii summed plus the range ({LIMIT} m, 3-D): struck at {inside:.2f} m, "
              f"refused at {beyond:.2f} m", flush=True)
        # PQ-439 review: the next held cast is accepted during the archer's
        # own arrival write. A trigger delays every arrival's wear write by
        # 0.6 s (12 ticks; a longer one passes the server's 800 ms lock and
        # 1000 ms statement timeouts behind the realm fence). PQ-444: not the
        # release's arrow writes, whose payload names the arrow ("AMMO"). From
        # 3.4 m the arrow flies 17 ticks, so the first shot's arrival write
        # starts at about tick 36 after its acceptance and is still pending
        # when the 40-tick interval lets the second go.
        def sql(statement):
            return run("docker", "exec", "-i", name, "psql", "-U", "n3e", "-d", "n3e", "-tAc", statement).strip()

        def delay(arrows_only):
            sql("CREATE OR REPLACE FUNCTION delay_wear() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
                f"IF (position(convert_to('AMMO', 'UTF8') IN NEW.payload) > 0) = {str(arrows_only).lower()} THEN "
                "PERFORM pg_sleep(0.6); END IF; RETURN NEW; END $$")
        delay(arrows_only=False)
        sql("CREATE TRIGGER delay_wear BEFORE INSERT ON durability_operations FOR EACH ROW "
            "EXECUTE FUNCTION delay_wear()")
        walk(a, target[0], target[2] + 3.4)
        a.pump(PAUSE)
        near_id = first(npc(a, TEMPLATES[0]["name"]), 1)
        quiver = arrows(a)
        attack = attack_now(a)
        sent = time.monotonic()
        w1 = send_shot(a, near_id)
        snaps, events = [], {}
        while time.monotonic() < sent + PAUSE:
            record(a, *a.receive(), snaps, events)
        w2 = send_shot(a, near_id)
        mark = len(seen_attacks)
        result, damage, more, more_events = collect(a, w1, seconds=8)
        snaps += more
        events.update(more_events)
        assert result in ("hit", "miss"), result
        shots.append((result, damage, attack))
        # The second is held, then released: the arrow is out, its result
        # comes at its arrival; a try now is refused by its own interval
        # (from its acceptance), not by the first shot's (40 ticks earlier).
        end = time.monotonic() + 4
        while not any(first(e[a.id], 30) == w2 and first(e[a.id], 14) == b"released" for _, e in snaps):
            assert time.monotonic() < end, "the second shot was never released"
            t, d = a.receive()
            record(a, t, d, snaps, events)
            assert not (t == 16 and first(d, 1) == w2), ("the second shot was refused", first(d, 2))
        w3 = send_shot(a, near_id)
        early, _, more, more_events = collect(a, w3)
        snaps += more
        events.update(more_events)
        result2, damage2, more, more_events = collect(a, w2, seconds=8)
        snaps += more
        events.update(more_events)
        assert result2 in ("hit", "miss"), result2
        shots.append((result2, damage2, (attack, *seen_attacks[mark:])))
        spent += 2
        settle(a, .3, snaps, events)
        at = {(first(e, 17), first(e, 5)): e for e in events.values()}
        assert all((s_, k) in at for s_ in (w1, w2) for k in (2, 6, 7)), sorted(at)
        tick = {k: first(e, 2) for k, e in at.items()}
        fly = flight_ticks(at[w1, 7])
        assert 15 <= fly <= 19, fly  # 3.4 m at 4 m/s: 17
        # The first arrow's write began (its landing, queued at its arrival,
        # starts in the arrival tick's command drain, before any network
        # command) at or before the second's acceptance and committed after
        # it.
        write_from = tick[w1, 7] + fly
        assert write_from <= tick[w2, 2] < tick[w1, 6], (write_from, tick)
        assert tick[w2, 2] - tick[w1, 2] >= 40, tick
        assert early == "cooldown", (early, tick)
        # The first arrow's landing left the newer cast's strike fields alone.
        between = [(t, e) for t, e in snaps if tick[w1, 6] < t < tick[w2, 7]]
        assert between and all((first(e[a.id], 10), first(e[a.id], 30), first(e[a.id], 14)) == (tick[w2, 2], w2, b"casting")
                               for _, e in between), [(t, first(e[a.id], 10), first(e[a.id], 14)) for t, e in between]
        assert tick[w2, 6] - tick[w2, 7] >= flight_ticks(at[w2, 7]), tick
        assert arrows(a) == quiver - 2, (arrows(a), quiver)
        print(f"PASS the next shot is accepted during the archer's own arrival write (PQ-439 review): with every arrival's wear "
              f"write delayed 0.6 s, the first arrow's write ran from tick {write_from} to its landing at "
              f"{tick[w1, 6]}, the second shot was accepted at tick {tick[w2, 2]} ({tick[w2, 2] - tick[w1, 2]} after "
              f"the first, not combat_pending or target_pending), the first landing left its cast's strike fields "
              f"('casting', tick {tick[w2, 2]}) for {len(between)} snapshots, a try after its release was cooldown "
              f"(its interval kept), both landed and spent {quiver} -> {quiver - 2} arrows", flush=True)
        # Another player's arrival write on the same target still refuses the
        # cast (target_pending): a second archer shoots NEAR from 3.4 m and
        # the first tries while that arrow's write is pending.
        w = peer("warden")
        w_state = bag(w)
        w_state = bag(w, 5, slot_of(w_state, BLADE), 0, w_state)
        wait(w, 10, lambda _: first(w.entities[w.id], 22) == 2)
        walk(w, target[0] + 3.4, target[2])
        w.pump(PAUSE)
        refused = []
        for _ in range(3):
            snaps, events = [], {}
            wseq = send_shot(w, first(npc(w, TEMPLATES[0]["name"]), 1))
            end = time.monotonic() + 4
            release = None
            while release is None:
                assert time.monotonic() < end, "the warden's shot was never released"
                record(a, *a.receive(), snaps, events)
                release = next((e for e in events.values() if first(e, 3) == w.id and first(e, 5) == 7
                                and first(e, 17) == wseq), None)
            # Its write starts flight ticks after the release (PQ-444: no
            # lead) and lasts about 12; try in its middle.
            time.sleep((flight_ticks(release) - 1 + 5) * .05)
            try_seq = send_shot(a, near_id)
            status, dealt, more, more_events = collect(a, try_seq, seconds=8)
            refused.append(status)
            assert status in ("target_pending", "hit", "miss"), status
            if status in ("hit", "miss"):  # sent after that write: a shot spent
                spent += 1
                shots.append((status, dealt, (attack, *seen_attacks[mark:])))
            w.pump(PAUSE)
            if status == "target_pending":
                break
        assert refused[-1] == "target_pending", refused
        w.logout()
        print(f"PASS another player's arrival write on the target still refuses the cast: target_pending "
              f"(tries {refused})", flush=True)
        # PQ-444 (D-224): a slow release write holds the release. Now only the
        # arrow writes are delayed 0.6 s: the shot stays 'casting' past its
        # landing tick and is released (its kind-7 event, its bag pushed) only
        # once its arrow write has committed, about 12 ticks late (at most
        # ranged_shot::DEFER, 20).
        delay(arrows_only=True)
        a.pump(PAUSE)
        quiver = arrows(a)
        attack = attack_now(a)
        seq = send_shot(a, near_id)
        result, damage, snaps, events = collect(a, seq, seconds=8)
        assert result in ("hit", "miss"), result
        spent += 1
        shots.append((result, damage, attack))
        settle(a, .3, snaps, events)
        at = {(first(e, 17), first(e, 5)): first(e, 2) for e in events.values()}
        assert all((seq, k) in at for k in (2, 6, 7)), sorted(at)
        late = at[seq, 7] - at[seq, 2]
        assert LAND + 10 <= late <= LAND + 20, (late, at)
        casting = [(t, e) for t, e in snaps if at[seq, 2] < t <= at[seq, 7]]
        assert max(t for t, _ in casting) > at[seq, 2] + LAND and all(
            first(e[a.id], 14) == b"casting" and first(e[a.id], 30) == seq for _, e in casting), \
            [(t, first(e[a.id], 14)) for t, e in casting]
        assert arrows(a) == quiver - 1, (arrows(a), quiver)
        sql("DROP TRIGGER delay_wear ON durability_operations; DROP FUNCTION delay_wear()")
        print(f"PASS a slow release write holds the release (PQ-444): with each arrow write delayed 0.6 s the shot "
              f"was released {late} ticks after its start (the marker at {LAND}), 'casting' until then, and landed "
              f"({result}); {quiver} -> {quiver - 1} arrows", flush=True)
        # PQ-444 (D-224): a release whose write finds too few arrows in the
        # locked durable bag fails the shot no_ammo at the release, as 1298's
        # flying phase fails (0046f3f1 returns 4): no release, no landing, the
        # cast cleared. The test empties the archer's arrow slot in Postgres
        # behind the server's back (the same revision, so its own bag still
        # shows the arrows and the acceptance passes), then puts it back.
        character = sql("SELECT id FROM characters WHERE name='Archer'")
        a.pump(PAUSE)
        quiver = arrows(a)  # this read also leaves the server's bag the durable one
        original = bytes.fromhex(sql(f"SELECT encode(state, 'hex') FROM character_bags WHERE character_id={character}"))
        hp5 = first(npc(a, TEMPLATES[0]["name"]), 7)
        sql(f"UPDATE character_bags SET state=decode('{without_arrows(original).hex()}', 'hex') "
            f"WHERE character_id={character}")
        mark = len(pushes)
        seq = send_shot(a, near_id)
        result, damage, snaps, events = collect(a, seq)
        settle(a, .5, snaps, events)
        assert (result, damage) == ("no_ammo", 0), (result, damage)
        assert not [e for e in events.values() if first(e, 5) in (6, 7) and first(e, 17) == seq], events
        cast = [(first(e[a.id], 10), t) for t, e in snaps if first(e[a.id], 30) == seq and first(e[a.id], 14) == b"casting"]
        assert cast and max(t for _, t in cast) >= cast[0][0] + LAND - 1, cast
        me = a.entities[a.id]
        assert (first(me, 10), first(me, 30)) == (0, 0), me
        assert first(npc(a, TEMPLATES[0]["name"]), 7) == hp5
        assert [(status, held_) for _, status, held_ in pushes[mark:]] == [(b"no_ammo", 0)], pushes[mark:]
        sql(f"UPDATE character_bags SET state=decode('{original.hex()}', 'hex') WHERE character_id={character}")
        assert arrows(a) == quiver, (arrows(a), quiver)
        print(f"PASS a release whose arrow write finds too few arrows fails the shot (PQ-444, 1298 0046f3f1 returns "
              f"4): '{result}' at the release (cast from tick {cast[0][0]}, 'casting' until {max(t for _, t in cast)}), "
              f"no release or landing event, the cast cleared, NEAR unharmed "
              f"({hp5}), the durable bag pushed with no arrows; restored to {quiver}", flush=True)
        walk(a, *PLAYER)
        # PQ-421 (D-218): each released shot took one arrow (PQ-444: at its
        # release, also the one cancelled in flight), the refused ones and the
        # ones cancelled before their release none; the rest go now, then the
        # shot is refused.
        assert arrows(a) == ARROWS - spent, (arrows(a), spent)
        counts = [ARROWS - spent]
        assert counts[-1] >= 1, counts
        while counts[-1] > 1:
            a.pump(PAUSE)
            attack = attack_now(a)
            shots.append((*collect(a, send_shot(a, first(npc(a, TEMPLATES[0]["name"]), 1)))[:2], attack))
            assert shots[-1][0] in ("hit", "miss"), shots
            counts.append(arrows(a))
        # PQ-444 (D-224): the last arrow. Its shot is released (the arrow
        # spent) and, while that arrow still flies (30 ticks at 6 m), the next
        # shot, sent once the interval has run, is refused no_ammo at its
        # acceptance, before the first lands, as 1298's client refuses the
        # cast once Ebenezer's flying phase has taken the arrow (0057f7f0
        # after 004b0792's bag update). Before PQ-444 it was accepted, its
        # arrow drawn, and refused only at its arrival.
        a.pump(PAUSE)
        attack = attack_now(a)
        target_id = first(npc(a, TEMPLATES[0]["name"]), 1)
        sent = time.monotonic()
        last = send_shot(a, target_id)
        snaps, events = [], {}
        while time.monotonic() < sent + PAUSE:
            record(a, *a.receive(), snaps, events)
        assert any(first(e[a.id], 30) == last and first(e[a.id], 14) == b"released" for _, e in snaps), "not released"
        after = send_shot(a, target_id)
        refused, _, more, more_events = collect(a, after)
        events.update(more_events)
        assert refused == "no_ammo", refused
        assert not [e for e in events.values() if first(e, 5) == 6 and first(e, 17) == last], "the last arrow landed first"
        assert not [e for e in events.values() if first(e, 5) == 2 and first(e, 17) == after], "the refused shot was cast"
        result, damage, _, _ = collect(a, last, seconds=8)
        assert result in ("hit", "miss"), result
        shots.append((result, damage, attack))
        counts.append(arrows(a))
        assert counts == list(range(ARROWS - spent, -1, -1)), counts
        print(f"PASS the last arrow is spent at its release (PQ-444): the next shot, sent while it flew, was refused "
              f"no_ammo at its acceptance (no cast), before the last arrow landed ({result})", flush=True)
        # PQ-422 (D-219): each of those shots dealt the type-2 skill hit's
        # damage for the archer's derived attack when it was sent (PQ-439: or,
        # for a shot sent while an earlier arrow flew, after that one's wear).
        bounds = [(r, d, attack, *skill_hit_damage(attack)) for r, d, attacks in shots
                  for attack in ([attacks] if isinstance(attacks, int) else
                                 [next((x for x in attacks if any(lo <= d <= hi or d == m for m, lo, hi in
                                                                  [skill_hit_damage(x)])), attacks[0])])]
        assert all(attack > 0 and r == "hit" and (d == miss or low <= d <= high)
                   for r, d, attack, miss, low, high in bounds), bounds
        print(f"PASS the ranged profile's type-2 skill hit (PQ-422, AI 0040d471 -> 00443a34): {len(shots)} landed "
              f"shots, all hits, each within its bounds for the archer's derived attack against defence 0, "
              f"AddDamage {SKILL_HIT['add_damage']} and AddDamagePlus {SKILL_HIT['add_damage_plus']} (damage, "
              f"attack, missed grade, lowest and highest hit): {[(d, a_, m_, lo, hi) for _, d, a_, m_, lo, hi in bounds]}; "
              f"the basic attack alone deals 0.85 to 1.15 x attack x 200 / 240 and can miss", flush=True)
        assert not [r for r in bag(a)[5] if first(fields(r), 2) == ARROW.encode()], "the emptied slot is vacant"
        a.pump(PAUSE)
        target = npc(a, TEMPLATES[0]["name"])
        hp = first(target, 7)
        assert a.action(first(target, 1)) == "no_ammo"
        assert a.action(first(target, 1)) == "no_ammo", "a refused shot spends no interval"
        a.pump(.5)
        assert first(npc(a, TEMPLATES[0]["name"]), 7) == hp
        a.logout()
        a = peer("archer", new=False)
        assert arrows(a) == 0 and first(a.entities[a.id], 22) == 2
        a.pump(PAUSE)
        assert a.action(first(npc(a, TEMPLATES[0]["name"]), 1)) == "no_ammo"
        print(f"PASS each released shot spends one arrow from the bag in its release's durable write (PQ-421, PQ-444, "
              f"1298 0046f3f1 / 004b0792): {ARROWS} granted, {spent} spent by the shots above (the one cancelled in "
              f"flight too; the ones cancelled before their release, cooldown, combat_pending, no_ammo and out-of-range "
              f"ones none), then {counts}; with none left the shot is refused as no_ammo (NEAR "
              f"unharmed at {hp}, no interval spent), also after a new login", flush=True)
        if os.environ.get("N3E_GRAPHICAL") != "1":
            a.logout()
            return
        # The second archer stands 16 m from NEAR with the blade worn.
        s = peer("scout")
        s_state = bag(s)
        s_state = bag(s, 5, slot_of(s_state, BLADE), 0, s_state)
        wait(s, 10, lambda _: first(s.entities[s.id], 22) == 2)
        walk(s, *SPOT)
        s.logout()
        # PQ-421: a third archer, at the spawn with all its arrows, shoots.
        b = peer("bowman")
        b_state = bag(b)
        b_state = bag(b, 5, slot_of(b_state, BLADE), 0, b_state)
        wait(b, 10, lambda _: first(b.entities[b.id], 22) == 2)
        walk(b, *BOW_SPOT)
        b.logout()
        a.logout()
        observer = peer("archer", new=False)

        def client(account, seconds, during=None):
            lines = []
            with tempfile.TemporaryDirectory(dir=OUT) as config:
                proc = subprocess.Popen(
                    ["build/client/n3e-test-client", str(package), "--connect", f"localhost:{listen}", "--ca",
                     "deploy/local/ca.pem", "--auto-login", "--world-smoke", str(seconds)],
                    env={**os.environ, "N3E_TEST_ACCOUNT": account, "N3E_TEST_PASSWORD": passwords[account],
                         "N3E_TEST_STAND_STILL": "1", "N3E_TEST_SHOWCASE_TARGET": "2.0",
                         "N3E_TEST_SHOWCASE_ATTACK": "3.0", "XDG_CONFIG_HOME": config},
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                reader = threading.Thread(target=lambda: lines.extend(proc.stdout), daemon=True)
                reader.start()
                seen = []
                while proc.poll() is None:
                    observer.pump(.1)
                    seen.append({i: dict(e) for i, e in observer.entities.items()})
                    if during:
                        during(seen[-1])
                reader.join(10)
            text = "".join(lines)
            (out / f"{account}.log").write_text(text)
            assert proc.returncode == 0, (proc.returncode, text[-1500:])
            target = re.search(r"^SHOWCASE_TARGET at=\S+ nearest=(\d+)$", text, re.M)
            assert target and re.search(r"^SHOWCASE_ATTACK at=\S+ target=[1-9]", text, re.M), text[-2000:]
            return text, int(target[1]), seen

        # The bowman at BOW_SPOT: Z selects NEAR (6 m), R shoots it from there.
        observer.logout()
        observer = peer("scout", new=False)
        text, chosen, seen = client("bowman", 12)
        quiver = [int(n) for n in re.findall(r"^RANGED_SHOT .* ammo=(\d+)$", text, re.M)]
        shots = [(float(d), tuple(float(v) for v in p.split(","))) for d, p in re.findall(
            r"^RANGED_SHOT seq=\d+ target=\d+ distance=(\S+) limit=\S+ position=(\S+) ammo=\d+$", text, re.M)]
        near = npc(observer, TEMPLATES[0]["name"])
        assert chosen == first(near, 1) and len(shots) >= 3, (chosen, shots, text[-2000:])
        assert all(5.5 < d < 6.5 for d, _ in shots), shots
        assert max(math.dist(p, shots[0][1]) for _, p in shots) < .05, shots
        assert "RANGED_TOO_FAR" not in text and "RANGED_NO_AMMO" not in text, text[-2000:]
        # PQ-421: the client counts its arrows down, one per shot (the
        # server's bag update). PQ-444 (D-224): the arrow goes at the release,
        # so a shot sent while the previous one's arrow still flies already
        # counts that arrow spent (before PQ-444 it still counted it).
        assert quiver[0] == ARROWS and quiver[-1] < ARROWS and all(0 <= x - y <= 1 for x, y in zip(quiver, quiver[1:])), quiver
        sent_ammo = [(int(r), int(n)) for r, n in re.findall(r"^RANGED_SHOT seq=(\d+) .* ammo=(\d+)$", text, re.M)]
        timed = {kind: {int(r): int(t) for r, t in re.findall(
            rf"^RANGED_{kind} actor=\d+ self=1 request=(\d+) tick=(\d+) hit=[01]$", text, re.M)}
            for kind in ("CAST_START", "RELEASED", "LANDED")}
        overlapping = [(n1, n2) for (r1, n1), (r2, n2) in zip(sent_ammo, sent_ammo[1:])
                       if r1 in timed["RELEASED"] and r1 in timed["LANDED"] and r2 in timed["CAST_START"]
                       and timed["CAST_START"][r2] < timed["LANDED"][r1]]
        assert overlapping and all(n1 - n2 == 1 for n1, n2 in overlapping), (sent_ammo, timed)
        archer = [v for snap in seen for i, v in snap.items() if first(v, 9) != 1 and i != observer.id]
        struck = {first(v, 10) for v in archer if first(v, 25) == first(near, 1) and first(v, 10)}
        moved = max(math.hypot(first(v, 3) - BOW_SPOT[0], first(v, 5) - BOW_SPOT[1]) for v in archer)
        assert len(struck) >= 3 and moved < .3, (len(struck), moved)
        print(f"PASS graphical client shoots from where it stands: Z then R on NEAR at {shots[0][0]:.2f} m sent "
              f"{len(shots)} shots (RANGED_SHOT) without walking (the server's position stayed within {moved:.2f} m "
              f"of where it logged in; {len(struck)} strikes on NEAR seen by another player), its arrows counting down "
              f"{quiver} (PQ-421)", flush=True)
        # PQ-420: the client stretched the cast clip to 0.9 s (its marker to
        # 0.72 s) and drew each of its held shots' hits at the landing event;
        # PQ-439 (D-223): the release comes LAND ticks after the shot's start
        # event, the landing the arrow's flight (about 30 ticks at 6 m) later.
        stretched = re.search(r"^RANGED_CAST profile=2 clip=(\d+) cast_ms=900 duration=(\S+) stretch=(\S+) blend=(\S+) "
                              r"marker=(\S+)$", text, re.M)
        assert stretched and [round(float(v), 4) for v in stretched.groups()[1:]] == [.9, .9, .2, .72], \
            (stretched and stretched.groups(), text[:2000])
        starts = {int(r): int(t) for r, t in re.findall(
            r"^RANGED_CAST_START actor=\d+ self=1 request=(\d+) tick=(\d+) hit=0$", text, re.M)}
        lands = {int(r): int(t) for r, t in re.findall(
            r"^RANGED_LANDED actor=\d+ self=1 request=(\d+) tick=(\d+) hit=[01]$", text, re.M)}
        releases = {int(r): int(t) for r, t in re.findall(
            r"^RANGED_RELEASED actor=\d+ self=1 request=(\d+) tick=(\d+) hit=0$", text, re.M)}
        paired = sorted(r for r in lands if r in starts and r in releases)
        assert len(paired) >= 2 and all(releases[r] - starts[r] == LAND for r in paired), (starts, releases, lands)
        # The bowman stands 6 m (within its walk's 0.05 m) from NEAR: 30 or
        # 31 ticks of flight. PQ-444 (D-224): the arrival's commit holds only
        # the wear (every hit wears the blade here), so a hit is published a
        # tick after the arrival.
        flown = sorted({lands[r] - releases[r] for r in paired})
        assert all(29 <= f <= 51 for f in flown) and flown[0] <= 32, (releases, lands)
        # The client sends its next shot once the interval has run, with the
        # arrow still in flight, not after its result (1298's 004659b0 and
        # 005819e0 test no flight: binary, by absence, PQ-439 evidence).
        sent = sorted(starts.values())
        spacing = [b_ - a_ for a_, b_ in zip(sent, sent[1:])]
        assert spacing and min(spacing) < LAND + flown[0] and min(spacing) >= INTERVAL_MS // 50, (spacing, flown)
        poses = re.findall(r"^RANGED_POSE request=(\d+) clip=(\d+) duration=(\S+)$", text, re.M)
        assert len(poses) >= 2 and all(int(c) == int(stretched[1]) and abs(float(d) - 1.1) < 1e-4 for _, c, d in poses), poses
        print(f"PASS graphical client plays the held shot as 1298's cast: the attack clip stretched to the cast "
              f"(duration 0.9 s, marker 0.72 s, RANGED_CAST), each of its {len(poses)} predicted shot poses 1.1 s "
              f"(cast + blend, RANGED_POSE), and {len(paired)} shots drawn from their start event to their release "
              f"{LAND} ticks later (the marker) and their landing {flown} ticks after that (RANGED_CAST_START, "
              f"RANGED_RELEASED, RANGED_LANDED; PQ-439); its shots went out {spacing} ticks apart (at least the "
              f"{INTERVAL_MS // 50}-tick interval, the closest while the previous arrow flew)", flush=True)
        cast_effects(text, starts, releases)
        flights(text, releases, first(near, 1))
        b = peer("bowman", new=False)
        walk(b, *CLOSE_SPOT)
        b.logout()
        reconcile_flights(observer, client, sql, delay, without_arrows, first(near, 1))
        # PQ-421: the first archer, at the spawn without arrows: R neither
        # shoots nor walks, and posts the ammo notice once an interval (1298's
        # 0057f7f0 text 0xfa7, before the range check).
        text, chosen, seen = client("archer", 10)
        dry = re.findall(r"^RANGED_NO_AMMO target=(\d+) item=(\S+) count=(\d+) notice='(.*)'$", text, re.M)
        near = npc(observer, TEMPLATES[0]["name"])
        assert chosen == first(near, 1) and len(dry) >= 2, (chosen, dry, text[-2000:])
        assert all(int(t) == chosen and i == ARROW and c == "1" and n == AMMO_NOTICE for t, i, c, n in dry), dry
        assert "RANGED_SHOT" not in text and "RANGED_TOO_FAR" not in text, text[-2000:]
        dry_archer = [v for snap in seen for i, v in snap.items() if first(v, 9) != 1 and i != observer.id]
        moved = max(math.hypot(first(v, 3) - PLAYER[0], first(v, 5) - PLAYER[1]) for v in dry_archer)
        shot = {first(v, 10) for v in dry_archer if first(v, 10)}
        assert moved < .3 and not shot, (moved, shot)
        print(f"PASS graphical client without arrows does not shoot: at {math.dist(PLAYER, (first(near, 3), first(near, 5))):.2f} m "
              f"from NEAR it neither walked ({moved:.2f} m) nor shot, and posted the package's ammo notice "
              f"{len(dry)} times (RANGED_NO_AMMO), once an interval (PQ-421)", flush=True)
        # The second archer, 16 m from NEAR: Z selects NEAR; R neither walks nor
        # shoots, and posts the notice once an interval.
        observer.logout()
        observer = peer("archer", new=False)
        text, chosen, seen = client("scout", 12)
        refused = re.findall(r"^RANGED_TOO_FAR target=(\d+) distance=(\S+) limit=(\S+) walking=0 notice='(.*)'$",
                             text, re.M)
        near = npc(observer, TEMPLATES[0]["name"])
        assert chosen == first(near, 1) and len(refused) >= 3, (chosen, refused, text[-2000:])
        assert all(int(t) == chosen and 15.5 < float(d) < 16.5 and float(lim) == LIMIT and n == NOTICE
                   for t, d, lim, n in refused), refused
        assert "RANGED_SHOT" not in text, text[-2000:]
        scout = [v for snap in seen for i, v in snap.items() if first(v, 9) != 1 and i != observer.id]
        moved = max(math.hypot(first(v, 3) - SPOT[0], first(v, 5) - SPOT[1]) for v in scout)
        swung = {first(v, 10) for v in scout if first(v, 10)}
        assert moved < .3 and not swung, (moved, swung)
        print(f"PASS graphical client does not chase a target beyond the ranged limit: at {float(refused[0][1]):.2f} m "
              f"it neither walked ({moved:.2f} m) nor struck, and posted the package's notice {len(refused)} times "
              f"(RANGED_TOO_FAR), once an interval", flush=True)
        observer.logout()
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
    assert (package / "ranged-attack.bin").read_bytes()[:4] == b"N3RH"
    check_readers(package)
    print("PASS N3RH package: both readers accept the ranged profile with its cast time, its arrows, its skill hit, "
          "its cast effect, its flight and its hold", flush=True)
    check_cast_effect_clip(package)
    check_flight_clip(package)
    live(package)
