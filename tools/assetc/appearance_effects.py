"""N3E2 appearance effects (PQ-211): effects drawn on equipped appearance keys.

An N3E2 file is an N3EF effects file (textures, clips, bindings) followed by
this section. Every point is in the player's bind (model) space and rigid to one
skeleton joint; the client skins it with the body (client/render/appearance_effects.h).
The KO adapter fills it from the hand-plug weapon effect (ko_weapon_fx.py); the
engine knows no KO IDs, tables or constants.

Section: u32 count (0..16), then per effect:
  u32 key (1..128, an N3V1 appearance key), u32 joint
  u32 frame count (1..64), u32 effect texture IDs, f32 frames per second
  u32 phase steps (1..10000), f32 phase step: start phase (rand % steps) x step s
  u32 source blend, destination blend (1..10), u32 render flags (11 bits)
  u32 copy count (0..4), per copy: f32 jitter weight (-1..1), u32 frame offset,
      u32 vertex count (3..3072, a triangle list), per vertex f32 x, y, z, u, v
  f32 jitter rate, amplitude: offset (frac(t x rate) x 2 - 1) x amplitude
  f32 x 6: the unit jitter axis's origin and tip
  f32 x 12: the tail box origin and its x, y, z edge ends
  f32 low, u32 steps (1..10000), f32 step: a tail point's edge fraction
  u32 tail count (0..4), string tail clip ('' without tails)
  u32 trace colour (ARGB; carried, not drawn)

N3E3 (PQ-315) is N3E2 whose effect section may be empty (0..16), followed by an
equipment glow section: u32 count (1..16), then per glow:
  u32 key (1..128, an N3V1 appearance key, at most once)
  f32 x 3: the emissive colour (0..1)
  f32 modulate: 1, 2 or 4 (the texture product's scale)
  u32 wave: 0 steady (intensity 1) or 1 pulse
  f32 rise, hold, fall, period: seconds, all 0 when steady, else
      0 < rise <= hold <= fall <= period <= 60
The client adds colour x intensity to the key's lighting, clamps at 1 and
multiplies the texture product by `modulate` (client/render/equipment_glow.h).
The KO adapter fills it from the 2233 client's equipment glow rule over the
player's 2145 tables (ko_glow_2233.py); the engine knows no KO IDs or tables.

N3E4 (PQ-342) is N3E3 whose glow section may be empty (0..16), followed by a
particle distance section: u32 count (1..64), then per rule:
  string clip: an appearance effect's tail clip that no binding names
  u32 texture, source blend, destination blend, render flags: the clip's
      particle batches (kind 1) it applies to, at most one rule per clip and
      batch material, at least one such batch in the clip
  u32 count (1..1024): the part's particle pool
  f32 near, far (0 < x <= 1000 m)
In those batches every record is an emission candidate: its birth is a sample
time (birth x rate an integer, within 1e-3) and no two records of one frame
share a birth. Each sample the client takes a candidate born then while the
candidates it took that were alive at the previous sample are at most the
target count and fewer than the pool, and draws the ones it took; the target
is the pool within `near` m of the camera, else trunc(pool x (far - d) / far)
at camera distance d (negative past far), and nothing is drawn at 0
(client/render/effects.h). The KO adapter fills it from the 2233 particle
tick's distances (ko_fx_tail_2233.py); the engine knows no KO IDs or values.

N3E5 (PQ-376, D-200) is N3E4 whose rule list may be empty (0..64), followed by
a sort section: u32 count (1..16), then per record:
  u32 key: an appearance effect of this file, at most once
  f32 x 3: the sort origin, in bind space, rigid to the effect's joint
  f32 bias (0..1000)
The client then sorts each of the effect's copies by the linear eye distance
to the origin moved by the copy's jitter, plus the bias, and each
camera-facing quad of its tail links on its own, by the linear eye distance to
the centroid of its first three corners (UV (0, 0), (1, 0), (1, 1));
everything in the effect pass is drawn far to near
(client/render/effects.h). An effect without a record keeps each copy at its
vertex centroid and each tail link at its newest point. The KO adapter fills it
from 1298's alpha list keys (00415910, 004840b0) with the plug origin and the
FX mesh's y extent (ko_fx_bake.py); the engine knows no KO IDs or values.
"""
import math
import struct
from common import count, f as floats, string, u


def f(*xs):
    return floats(xs)


def _finite(values, bound, what):
    for v in values:
        if not isinstance(v, (int, float)) or not math.isfinite(v) or abs(v) > bound:
            raise ValueError(f'appearance effect {what}')


def section(entries, textures, clips, keys):
    """Serialize `entries` (dicts, see the module text). `textures` is the effect
    texture count, `clips` the clip names, `keys` the appearance key count."""
    count(len(entries), 16, 0)
    data = u(len(entries))
    seen, vertices = set(), 0
    for e in entries:
        if not 1 <= e['key'] <= keys or e['key'] in seen or not 0 <= e['joint'] <= 255:
            raise ValueError('appearance effect key/joint')
        seen.add(e['key'])
        frames = e['frames']
        count(len(frames), 64)
        if any(not 0 <= t < textures for t in frames):
            raise ValueError('appearance effect frame')
        if not 0 < e['fps'] <= 120 or not 1 <= e['phase_steps'] <= 10000 or not 0 <= e['phase_step'] \
                or e['phase_steps'] * e['phase_step'] > 10:
            raise ValueError('appearance effect timing')
        if any(b not in range(1, 11) for b in e['blend']) or e['flags'] & ~0x7ff:
            raise ValueError('appearance effect material')
        count(len(e['copies']), 4, 0)
        data += u(e['key']) + u(e['joint']) + u(len(frames)) + b''.join(u(t) for t in frames)
        data += f(e['fps']) + u(e['phase_steps']) + f(e['phase_step'])
        data += u(e['blend'][0]) + u(e['blend'][1]) + u(e['flags']) + u(len(e['copies']))
        for c in e['copies']:
            n = len(c['vertices'])
            count(n, 3072, 3)
            if n % 3 or not -1 <= c['jitter'] <= 1 or not 0 <= c['frame_offset'] < len(frames):
                raise ValueError('appearance effect copy')
            vertices += n
            if vertices > 8192:
                raise ValueError('appearance effect vertex budget')
            data += f(c['jitter']) + u(c['frame_offset']) + u(n)
            for v in c['vertices']:
                if len(v) != 5:
                    raise ValueError('appearance effect vertex')
                _finite(v[:3], 1000, 'position')
                _finite(v[3:], 1024, 'UV')
                data += f(*v)
        if not 0 <= e['jitter_rate'] <= 100 or not 0 <= e['jitter_amplitude'] <= 1:
            raise ValueError('appearance effect jitter')
        data += f(e['jitter_rate']) + f(e['jitter_amplitude'])
        points = list(e['jitter']) + list(e['tail_box'])
        if len(points) != 6 or any(len(p) != 3 for p in points):
            raise ValueError('appearance effect reference points')
        for p in points:
            _finite(p, 1000, 'position')
            data += f(*p)
        low, steps, step = e['tail_low'], e['tail_steps'], e['tail_step']
        if not 0 <= low or not 1 <= steps <= 10000 or not 0 <= step or low + (steps - 1) * step > 1 + 1e-4:
            raise ValueError('appearance effect tail range')
        data += f(low) + u(steps) + f(step)
        count(e['tails'], 4, 0)
        if (e['tail_clip'] in clips) != bool(e['tails']) or (not e['tails'] and e['tail_clip']):
            raise ValueError('appearance effect tail clip')
        data += u(e['tails']) + string(e['tail_clip'])
        if not 0 <= e['trace_color'] <= 0xffffffff:
            raise ValueError('appearance effect trace colour')
        data += u(e['trace_color'])
    return data


def glow_section(glows, keys, least=1):
    """Serialize the N3E3 glow records (dicts: key, color, modulate, wave, rise,
    hold, fall, period); `keys` is the appearance key count; N3E4 allows none
    (`least` 0)."""
    count(len(glows), 16, least)
    data, seen = u(len(glows)), set()
    for g in glows:
        if not 1 <= g['key'] <= keys or g['key'] in seen:
            raise ValueError('appearance glow key')
        seen.add(g['key'])
        color = list(g['color'])
        if len(color) != 3:
            raise ValueError('appearance glow colour')
        if any(not isinstance(c, (int, float)) or not math.isfinite(c) or not 0 <= c <= 1 for c in color):
            raise ValueError('appearance glow colour')
        if g['modulate'] not in (1, 2, 4):
            raise ValueError('appearance glow modulate')
        timing = [g['rise'], g['hold'], g['fall'], g['period']]
        if any(not isinstance(t, (int, float)) or not math.isfinite(t) or abs(t) > 60 for t in timing):
            raise ValueError('appearance glow timing')
        if g['wave'] == 0:
            if any(timing):
                raise ValueError('appearance glow timing')
        elif g['wave'] == 1:
            rise, hold, fall, period = timing
            if not 0 < rise <= hold <= fall <= period <= 60:
                raise ValueError('appearance glow timing')
        else:
            raise ValueError('appearance glow wave')
        data += u(g['key']) + f(*color) + f(g['modulate']) + u(g['wave']) + f(*timing)
    return data


def thinning_section(rules, scan, entries, least=1):
    """Serialize the N3E4 particle distance rules (dicts: clip, texture, blend,
    flags, count, near, far) against `scan` (_scan's result) and the effect
    `entries` (a rule's clip must be one of their tail clips); N3E5 allows
    none (`least` 0)."""
    count(len(rules), 64, least)
    tails = {e['tail_clip'] for e in entries if e['tails']}
    data, seen = u(len(rules)), set()
    for r in rules:
        clip = scan['clips'].get(r['clip'])
        if clip is None or r['clip'] not in tails or r['clip'] in scan['bound']:
            raise ValueError('appearance tail particle rule clip')
        key = (r['texture'], *r['blend'], r['flags'])
        if not 0 <= r['texture'] < scan['textures'] or len(r['blend']) != 2 \
                or any(b not in range(1, 11) for b in r['blend']) or r['flags'] & ~0x7ff:
            raise ValueError('appearance tail particle rule material')
        if (r['clip'], key) in seen:
            raise ValueError('duplicate appearance tail particle rule')
        seen.add((r['clip'], key))
        count(r['count'], 1024)
        for v in (r['near'], r['far']):
            if not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 < v <= 1000:
                raise ValueError('appearance tail particle rule distance')
        found = False
        for frame in clip['frames']:
            births = []
            for batch in frame:
                if batch[0] == 1 and tuple(batch[1:5]) == key:
                    found = True
                    births += batch[5]
            samples = [b * clip['rate'] for b in births]
            if any(b < 0 or abs(x - round(x)) > 1e-3 for b, x in zip(births, samples)) \
                    or len({round(x) for x in samples}) != len(samples):
                raise ValueError('appearance tail particle rule candidates')
        if not found:
            raise ValueError('appearance tail particle rule batch')
        data += string(r['clip']) + b''.join(u(n) for n in key) + u(r['count']) + f(r['near'], r['far'])
    return data


def sort_section(sorts, entries):
    """Serialize the N3E5 sort records (dicts: key, origin, bias) on the
    effect `entries`."""
    count(len(sorts), 16)
    effects = {e['key'] for e in entries}
    data, seen = u(len(sorts)), set()
    for r in sorts:
        if r['key'] not in effects or r['key'] in seen:
            raise ValueError('appearance effect sort key')
        seen.add(r['key'])
        origin = list(r['origin'])
        if len(origin) != 3:
            raise ValueError('appearance effect sort origin')
        _finite(origin, 1000, 'sort origin')
        bias = r['bias']
        if not isinstance(bias, (int, float)) or not math.isfinite(bias) or not 0 <= bias <= 1000:
            raise ValueError('appearance effect sort bias')
        data += u(r['key']) + f(*origin) + f(bias)
    return data


def n3e5(n3ef, entries, glows, rules, sorts, keys):
    """An N3EF file's bytes as N3E5: `entries` (0..16 effects), `glows`
    (0..16), particle distance `rules` (0..64) and the sort records `sorts`
    (1..16) on the entries."""
    if n3ef[:4] != b'N3EF':
        raise ValueError('N3EF required')
    scan = _scan(n3ef, detail=True)
    return (b'N3E5' + n3ef[4:] + section(entries, scan['textures'], set(scan['clips']), keys)
            + glow_section(glows, keys, 0) + thinning_section(rules, scan, entries, 0) + sort_section(sorts, entries))


def n3e4(n3ef, entries, glows, rules, keys):
    """An N3EF file's bytes as N3E4: `entries` (0..16 effects), `glows` (0..16)
    and the particle distance `rules` (1..64) on their tail clips."""
    if n3ef[:4] != b'N3EF':
        raise ValueError('N3EF required')
    scan = _scan(n3ef, detail=True)
    return (b'N3E4' + n3ef[4:] + section(entries, scan['textures'], set(scan['clips']), keys)
            + glow_section(glows, keys, 0) + thinning_section(rules, scan, entries))


def n3e3(n3ef, entries, glows, keys):
    """An N3EF file's bytes as N3E3: `entries` (0..16 effects) and `glows`."""
    if n3ef[:4] != b'N3EF':
        raise ValueError('N3EF required')
    textures, clips = _scan(n3ef)
    return b'N3E3' + n3ef[4:] + section(entries, textures, clips, keys) + glow_section(glows, keys)


def n3e2(n3ef, entries, keys):
    """An N3EF file's bytes as N3E2 with `entries` appended."""
    if n3ef[:4] != b'N3EF':
        raise ValueError('N3EF required')
    textures, clips = _scan(n3ef)
    return b'N3E2' + n3ef[4:] + section(entries, textures, clips, keys)


def _scan(data, detail=False):
    """Texture count and clip names of an N3EF file (the client's reader order).
    With `detail` (N3E4): a dict of the texture count, each clip's rate and, per
    frame, its batches as (kind, texture, source, destination, flags, births of
    a particle batch's records), and the clip names bindings use."""
    at = 4

    def take(n):
        nonlocal at
        if at + n > len(data):
            raise ValueError('truncated N3EF')
        at += n
        return data[at - n:at]

    def one():
        return struct.unpack('<I', take(4))[0]
    textures = one()
    for _ in range(textures):
        w, h = one(), one()
        take(w * h * 4)
    names, clips = set(), {}
    for _ in range(one()):
        name = take(one()).decode()
        names.add(name)
        _, rate = one(), one()
        frames = []
        for _ in range(one()):
            frame = []
            for _ in range(one()):
                kind = one()
                material = [one(), one(), one(), one()]
                n = one()
                records = take(n * (11 if kind else 9) * 4)
                if detail:
                    # A quad's birth is its eleventh float.
                    births = [struct.unpack_from('<f', records, 44 * k + 40)[0] for k in range(n)] if kind else []
                    frame.append((kind, *material, births))
            frames.append(frame)
        if detail:
            clips[name] = dict(rate=rate, frames=frames)
    if not detail:
        return textures, names
    bound = set()
    for _ in range(one()):
        one()
        take(one())
        one(), one()
        for _ in range(one()):
            bound.add(take(one()).decode())
    return dict(textures=textures, clips=clips, bound=bound)
