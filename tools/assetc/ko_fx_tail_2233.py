"""The 2233 weapon effect's tail as an N3E2 tail clip (PQ-341), a 2233/2145
addition: KO 1298's tail path (ko_fx_bake.appearance_effect) is unchanged.

Evidence: docs/implementation/evidence/pq-341-skeletal-plug-weapon-effect-tail-2233.md.
Binary basis is the 2233 client image (static analysis, PQ-314, a secondary
reference); reading the player's 2145 fx pack with it is an inference.

- InitFX (00437510) loads the tail (fx.tbl id + 1, +0x22c), triggers it and
  duplicates it twice (+0x230, +0x234, bundle vtable +0x28 0057fc10, which
  copies every field these parts use); each copy's target scale (+0x168) is
  (FX mesh y + z extent) x 0.7 (00b907d0), as 1298's 00415370. RenderFX
  (004304c0) moves each copy every frame to min + extent x (0.25 + (rand % 50)
  / 100) of the FX mesh box (00b90770, 00b90778) on plug x joint, then ticks it
  (+0x24, 00580050) and draws it (0057f9c0). n3e plays this as the N3E2 tail
  links (ko_weapon_fx), one box point per 1/30 s sample.
- A particle part (vtable 00b973b4; tick 00592900, emitters 00590570 kind 1
  and 005915e0 kind 2, particle tick 0058d150, render 0058e880): see
  particles() below; its camera-distance thinning (PQ-342) is a client rule
  over the cooked emissions: see thinning() below. A mesh part (vtable
  00b9746c; tick 0059a6f0, rotation 00599920, scale 0059a1f0, position
  00599ed0, render 00599580) draws a CN3FXShape (vtable 00b9731c; load
  0058bfb0, part load 0058c630): see mesh() below.

What the cook cannot confirm or draw it refuses, naming the field; what it
draws differently is in the evidence record (Limits).
"""
import math
import pathlib
import random
import struct
import ko
import ko_character as character
import ko_fx
import ko_fx_bake
from common import f, u, string

RATE = ko_fx_bake.RATE
# The longest link n3e plays: a clip is at most 20 s (N3EF, the client reader),
# a link emits for the first half of it.
MAX_LINK = 10
# PQ-342: 00592900's distances when a part's version-9 value is not positive
# (the constructor 0058ef60 zeroes them): near 10.0 (00b8fbb8), far 30.0
# (00b8fe4c). n3e bounds a part's own value to (0, MAX_DISTANCE] m.
NEAR, FAR, MAX_DISTANCE = 10.0, 30.0, 1000.0
# The client's record bound for one batch (client/assets/assets.cpp).
BATCH_RECORDS = 8192


def _refuse(what, part=None):
    raise ValueError('2233 weapon effect tail %s n3e does not draw%s' % (what, '' if part is None else
                                                                         ' (part %d)' % part))


def shape(source, name):
    """A CN3FXShape as 2233 loads it (0058bfb0: CN3Transform's load 0045eca0,
    then its parts, 0058c630), read from `source`: each part names its mesh and
    textures, which 0058c630 finds in the shape's own folder (_splitpath of the
    shape's name, the file's name and extension, _makepath). n3e draws one
    texture per part (texture animation refused), the shape at the origin with
    no rotation or translation keys and a uniform scale track (its frame count,
    0045eca0, at 30 keys a second only). Returns (frames, scale track, parts)."""
    r = character.Reader(source.get(name))
    r.string()
    position, rotation, scale = r.floats(3), r.floats(4), r.floats(3)
    keys = [character.key(r, k) for k in (0, 1, 0)]
    if [abs(v) for v in position] != [0, 0, 0] or rotation != [0, 0, 0, 1] or scale != [1, 1, 1]:
        _refuse('shape transform')
    if keys[0] and any(abs(v) for value in keys[0]['values'] for v in value) \
            or keys[1] and any(value != [0, 0, 0, 1] for value in keys[1]['values']):
        _refuse('shape translation or rotation keys')
    if keys[2] and any(not value[0] == value[1] == value[2] or value[0] < 0 for value in keys[2]['values']):
        _refuse('shape scale keys that are not uniform')
    if any(k and k['rate'] != 30 for k in keys):
        # 0045eca0 takes the frame count from each track's count and rate; at
        # 30 keys a second both readings of it give the count.
        _refuse('shape key rate')
    frames = max([len(k['values']) for k in keys if k] + [0])
    if r.string() or r.string():
        _refuse('shape collision meshes')
    n = r.integer()
    if not 1 <= n <= 16:
        raise ValueError('2233 FX shape part count')
    folder = pathlib.PurePosixPath(name.replace('\\', '/')).parent
    parts = []
    for _ in range(n):
        pivot = r.floats(3)
        mesh_name = str(folder / pathlib.PurePosixPath(r.string().replace('\\', '/')).name)
        mesh = ko.import_mesh(None, 1.0, data=source.get(mesh_name))
        material = r.unpack('17f6I')
        if material[:4] != [1, 1, 1, 1] or r.integer() != 1:
            _refuse('shape material or texture animation')
        r.floats(1)
        texture = str(folder / pathlib.PurePosixPath(r.string().replace('\\', '/')).name)
        parts.append(dict(pivot=pivot, mesh=mesh, texture=texture))
    if any(r.unpack('5i')):
        _refuse('shape events')
    r.end()
    return frames, keys[2], parts


def scale_key(track, frame, last=1.0):
    """2233's key sampler (0044b450): index trunc(frame x rate / 30), the last
    key at the count, otherwise key i blended toward key i + 1 by (frame -
    i x 30 / rate) / (30 / rate), which runs below 0 for a frame in (-1, 0)
    (the mesh's wrap gives one, 0059a6f0). `last` without a track, or for an
    index below 0 or past the count (the sampler returns false and the
    transform keeps its scale; the wrap gives -1 when f + 1 is a whole number
    of cycles)."""
    if track is None:
        return last
    values = [v[0] for v in track['values']]
    at = frame * track['rate'] / 30
    i = int(at)  # C truncation, toward zero
    if not 0 <= i <= len(values):
        return last
    if i == len(values):
        return values[-1]
    t = at - i
    return values[i] + (values[min(i + 1, len(values) - 1)] - values[i]) * t


def mesh_frame(meshfps, age, frames, wrap):
    """0059a6f0: f = meshfps x age; past frames - 1 it is cut to frames - 1, or,
    with the version-6 byte (+0x3d5) and a frame count, f - frames x
    trunc((f + 1) / frames) (assembly 0059aaf6-0059ab62)."""
    value = meshfps * age
    if value > frames - 1:
        if wrap and int(frames):
            value -= frames * int((value + 1) / frames)
        else:
            value = frames - 1
    return value


def euler(angles):
    """004674c0: the rows of Rx x Ry x Rz (row vectors, sin 00ac7b50, cos
    00ac7a20) for angles (x, y, z)."""
    sx, cx = math.sin(angles[0]), math.cos(angles[0])
    sy, cy = math.sin(angles[1]), math.cos(angles[1])
    sz, cz = math.sin(angles[2]), math.cos(angles[2])
    return [[cy * cz, cy * sz, -sy], [sx * sy * cz - cx * sz, sx * sy * sz + cx * cz, sx * cy],
            [cx * sy * cz + sx * sz, cx * sy * sz - sx * cz, cx * cy]]


def _common(d, i):
    if d['ground'] or d['flags'] & ~(199 | 16 | 256 | 512 | 1024) or d['flags'] & 66 != 66:
        _refuse('ground or render flags', i)
    if d['cycle'] != [0, 0] or d['texture2'] or d['life']:
        _refuse('on/off cycle, second texture or part life', i)
    if any(d['velocity']) or any(d['acceleration']):
        _refuse('part motion', i)


def mesh(d, i, source, texture, scale, length):
    """A mesh part's triangles for each 1/30 s frame of a link (`length` s),
    relative to the tail point. 0059a6f0 sets the shape's frame (mesh_frame;
    the version-6 byte wraps it), 00599920 its matrix to Rx x Ry x Rz of age x
    the part's rotation (004674c0, the bundle's direction being +z), 0059a1f0
    multiplies it by the part's scale plus age x its scale velocity, times the
    bundle's target scale when its scale flag is set (+0x164, +0x168), cut at
    0, and 00599ed0 places it at the tail point plus the part's position; the
    shape (00589fc0) puts its keys' scale before that and each part
    (00589de0) its pivot before both. Drawn white at full alpha (0059c830 on
    the vertex colours, the fade at its initial 0xffffffff with no fade-in or
    life) with the part's blends and flags and the shape part's texture.
    Refused: a uv scroll (+0x38c), scale acceleration, a camera-facing turn
    (+0x3d7), the other fade (+0x3d4), a second mesh, part textures, a non-
    uniform scale, a fade-in, and a mesh that stops on its last frame (links
    would replay it)."""
    _common(d, i)
    if d['uvdir'] or d['uv'] != [0, 0] or any(d['scale_accel']) or d['v7'] or d['v8'] or d['mesh2'] \
            or d['textures'] or d['fadein']:
        _refuse('mesh uv scroll, scale acceleration, turn, fade, second mesh or textures', i)
    if not d['scale'][0] == d['scale'][1] == d['scale'][2] or not d['scale_vel'][0] == d['scale_vel'][1] \
            == d['scale_vel'][2]:
        _refuse('non-uniform mesh scale', i)
    frames, track, parts = shape(source, d['mesh'])
    if track is not None and not d['v6']:
        _refuse('mesh that stops on its last frame', i)
    for p in parts:
        p['texture_index'] = texture(p['texture'], source)
    k = scale if scale is not None else 1.0
    out, keyed = [], 1.0  # the shape's own scale, (1, 1, 1)
    for frame in range(round(length * RATE)):
        age = frame / RATE - d['start']
        if age < 0:
            out.append([])
            continue
        keyed = scale_key(track, mesh_frame(d['meshfps'], age, frames, d['v6']), keyed)
        size = max(0.0, (d['scale'][0] + age * d['scale_vel'][0]) * k)
        m = euler([age * a for a in d['rotation']])
        batches = {}
        for p in parts:
            records = batches.setdefault((0, p['texture_index'], *d['blend'], d['flags']), [])
            for index in p['mesh']['indices']:
                v = p['mesh']['vertices'][index]
                # KO space (the mesh importer reflects z), pivot, keyed scale.
                q = [(v[0] + p['pivot'][0]) * keyed, (v[1] + p['pivot'][1]) * keyed,
                     (-v[2] + p['pivot'][2]) * keyed]
                w = [sum(q[r] * m[r][c] for r in range(3)) * size + d['position'][c] for c in range(3)]
                records.append([w[0], w[1], -w[2], v[6], v[7], 1, 1, 1, 1])
        out.append(list(batches.items()))
    return out


def thinning(d, i):
    """PQ-342: a particle part's camera-distance rule, or None. 2233's particle
    tick (00592900, assembly 005929ac-00592a37) sets the live count (+0x42c)
    every tick, unless the version-6 byte (+0x464) is set, from the camera's
    distance d (s_CameraData, which CN3Camera::Apply 0045c040 copies) to the
    part's bundle (+0x68, the tail copy 0057fc10 made, whose position RenderFX
    004304c0 sets each frame): the count (+0x428) when d < near, else
    trunc(count x (far - d) / far), which is negative past far; near is the
    version-9 value +0x694 when positive, else 10.0 (00b8fbb8), far +0x698 when
    positive, else 30.0 (00b8fe4c); the constructor (0058ef60) zeroes both and
    the copy (00593a90) carries them. An emission (00592740) happens only while
    the live particles (+0x448) are at most that count, and takes the batch
    from the free pool of `count` particles (005901b0, 00590570, 005915e0);
    live particles are never cut; the render (0058e880) draws them all unless
    the count is 0. Refused (n3e's guards): a value past MAX_DISTANCE or not
    finite, and a batch above 1 (the client knows a candidate by its birth
    sample alone)."""
    if d['v6']:
        return None
    values = [struct.unpack('<f', struct.pack('<I', v))[0] for v in d['v9']]
    if any(not math.isfinite(v) or v > MAX_DISTANCE for v in values):
        _refuse('particle camera distance past %g m' % MAX_DISTANCE, i)
    if d['batch'] != 1:
        _refuse('thinned particle batch other than 1', i)
    near, far = (v if v > 0 else default for v, default in zip(values, (NEAR, FAR)))
    return dict(count=d['count'], near=near, far=far)


def particles(d, i, source, texture, scale, length, seed, thin=None):
    """A particle part's quads for each 1/30 s frame of a link: emitted for the
    link's first `length` s, then left to finish. As 1298's (ko_fx_bake.
    sample_part) where 2233 does the same: the emission every tick whose time
    since the last reaches the delay (00592900, the first tick at once), up to
    the batch and the pool's free particles; a particle's life and size drawn
    between the part's two values in either order (0058fef0, 00590420); its
    offset drawn in the min-max box, turned from +z to the part's direction
    (0058e160, 009e4b88); kind 1 (00590570) the 1298 spread direction x speed;
    the bundle's target scale on the size, the box and, for kind 1, the
    velocity (when its scale flag is set). Kind 2 (005915e0, assembly
    00591e87-00591fa5): the velocity is speed x the unit vector from the turned
    offset to the turned target point (the three parameters), set after the
    scale, so unscaled. 0058d150 places it at its birth point plus the offset
    turned about the direction by age x the rotation, less the gravity drop,
    sized (size + age x size velocity, cut at 0) and turned by age x the texture
    rotation, faded in and out. Refused: a direction other than +y (the turn
    about it is the 1298 sampler's y turn; 0058e160 negates the vectors of a
    zero one), colours, an animated mesh
    emitter, more than one texture (the frame 0058d150 sets is not read), the
    y-facing quad (+0x465), the extra turn (+0x466 and its three values), the
    version-10 fields.

    PQ-342: with a `thin` rule (thinning()) every emission's batch is written,
    the candidates the pool would refuse too, and the client decides which to
    draw (the pool and 00592900's count, client/render/effects.h). The ones the
    full pool takes draw from the part's generator exactly as without a rule, the
    others from a second one, so at full count a chain's first link draws the
    same particles (a later link shares the copy's pool with the older one and
    may take others). Returns (the frames, the texture id)."""
    _common(d, i)
    if d['colors'] or d['animation'] or d['textures'] != 1 or d['v7'] or any(d['v8']) or any(d['v10']):
        _refuse('particle colours, mesh emitter, texture sequence, y-facing quad, extra turn or version-10 '
                'fields', i)
    if d['direction'][0] or d['direction'][2] or d['direction'][1] <= 0:
        _refuse('particle direction other than +y', i)
    if d['emit'] == 1 and not 0 <= d['emit_param'][0] <= 360:
        _refuse('particle spread', i)

    def turned(v):
        # The rotation from +z to +y (axis -x, a quarter turn): (x, z, -y).
        return [v[0], v[2], -v[1]]
    tex = texture(d['texture'] + '0000.dxt', source)
    k = scale if scale is not None else 1.0
    pooled_rng, spare_rng = random.Random(seed), random.Random(seed ^ 0x2233342)
    live, out = [], []
    since = d['delay']
    fadein, fadeout = d['fadein'], d['fadeout']
    for frame in range(round(2 * length * RATE)):
        t = frame / RATE
        records = []
        if t >= d['start'] and t < length:
            since += 1 / RATE
            if since + 1e-7 >= d['delay']:
                since = 0
                free = d['count'] - sum(p['pooled'] for p in live)
                for n in range(d['batch'] if thin else min(d['batch'], free)):
                    pooled = n < free
                    rng = pooled_rng if pooled else spare_rng
                    draw = lambda low, high: low + (high - low) * rng.randrange(100) / 100  # noqa: E731
                    life, size = draw(*d['particle_life']), draw(*d['size']) * k
                    offset = turned([draw(a, b) * k for a, b in zip(d['min'], d['max'])])
                    if d['emit'] == 1:
                        spread = d['emit_param'][0]
                        a = math.radians(rng.randrange(int(spread)) - spread / 2) if spread else 0
                        b = float(rng.randrange(360))  # radians, as 1298's
                        v = turned([math.sin(a) * math.cos(b), math.sin(a) * math.sin(b), math.cos(a)])
                        velocity = [x * d['speed'] * k for x in v]
                    else:
                        target = turned(list(d['emit_param']))
                        v = [target[c] - offset[c] for c in range(3)]
                        n_ = math.sqrt(sum(x * x for x in v))
                        velocity = [x / n_ * d['speed'] if n_ else 0.0 for x in v]
                    live.append(dict(born=t, life=life, size=size, pos=offset, velocity=velocity, drop=0.,
                                     drop_speed=0., pooled=pooled))
        kept = []
        for p in live:
            a = t - p['born']
            total = p['life'] + fadein + fadeout
            if a >= total or total <= 0:
                continue
            kept.append(p)
            angle = a * d['rotate']
            x, y, z = p['pos']
            c, s = math.cos(angle), math.sin(angle)
            centre = [d['position'][0] + c * x + s * z, d['position'][1] + y - p['drop'],
                      -(d['position'][2] - s * x + c * z)]
            alpha = ko_fx_bake.fade(a, p['life'], fadein, fadeout)
            sizes = [max(0.0, p['size'] + a * d['size_velocity_' + axis]) for axis in ('x', 'y')]
            records.append(centre + sizes + [a * d['texture_rotate'], 1, 1, 1, alpha, p['born']])
            for c3 in range(3):
                p['pos'][c3] += p['velocity'][c3] / RATE
            p['drop_speed'] += d['gravity'] / RATE
            p['drop'] += p['drop_speed'] / RATE
        live = kept
        if len(records) > BATCH_RECORDS:
            _refuse('particle batch past %d records' % BATCH_RECORDS, i)
        out.append([((1, tex, *d['blend'], d['flags']), records)] if records else [])
    return out, tex


def link_seconds(tail, meshes):
    """The link n3e plays: the shortest of 1..MAX_LINK s in 1/30 s steps that
    every particle outlives no more than (each link's particles finish in its
    second half) and that holds a whole number of every wrapping mesh's frame
    cycles (frames / meshfps), so a link restarting the shape's frames carries
    on where 2233's would be. None when there is none."""
    longest = max([max(p['particle_life']) + p['fadein'] + p['fadeout'] for p in tail['parts']
                   if p['kind'] == 1] + [0])
    for n in range(RATE, MAX_LINK * RATE + 1):
        seconds = n / RATE
        if seconds + 1e-9 < longest:
            continue
        if all(abs(x - round(x)) < 1e-6 for x in (seconds * fps / frames for fps, frames in meshes)):
            return seconds
    return None


def tail_clip(source, texture, spec, key):
    """The N3E2 tail clip of a '2233' spec's tail bundle (spec['tail'], read
    with ko_fx's 2233 layout from `source`): (clip bytes, report). Each part is
    sampled over a link (link_seconds) and the clip is two links long, so a
    link emits for its first half; mesh triangles are written only for the
    first half, which is all the client draws of a link (its stop). The
    bundle must be endless, still and plain (no velocity, life, static byte or
    field 2233 added); parts are particles (kind 1) or meshes (kind 3). PQ-342:
    the report's `thinning` lists each particle part's camera-distance rule
    (thinning(): its batch's texture, blends and flags, count, near, far), which
    the caller writes as N3E4 rules on the clip."""
    tail = ko_fx.bundle(source.get(spec['tail']), '2233')
    if tail['velocity'] or tail['static'] or tail['life'] or any(tail['extra'].values()):
        _refuse('bundle motion, life or fields')
    # 00580050: a part starts when the bundle's elapsed time reaches its start.
    scale = spec['geometry']['tail_scale'] if tail['scale'] else None
    meshes = []
    for i, d in enumerate(tail['parts']):
        if d['kind'] not in (1, 3):
            _refuse('part kind %d' % d['kind'], i)
        if d['kind'] == 3:
            frames, track, _ = shape(source, d['mesh'])
            if track is not None:
                meshes.append((d['meshfps'], frames))
    seconds = link_seconds(tail, meshes)
    if seconds is None:
        _refuse('link: no link of 1-%d s holds the particles and whole mesh cycles' % MAX_LINK)
    frames_out = [[] for _ in range(round(2 * seconds * RATE))]
    rules, materials = [], []
    for i, d in enumerate(tail['parts']):
        if d['kind'] == 3:
            sampled = mesh(d, i, source, texture, scale, seconds)
        else:
            thin = thinning(d, i)
            sampled, tex = particles(d, i, source, texture, scale, seconds, spec['tail_id'] * 31 + i, thin)
            material = (tex, *d['blend'], d['flags'])
            materials.append((material, thin is not None))
            if thin:
                rules.append(dict(thin, texture=material[0], blend=list(material[1:3]), flags=material[3]))
        for frame, batches in zip(frames_out, sampled):
            frame.extend(batches)
    # The client applies a rule to every particle batch of the clip with its
    # texture and render state (n3e's own guard: one part per such batch).
    if any(thin and sum(m == material for m, _ in materials) > 1 for material, thin in materials):
        _refuse('thinned particle part sharing its texture and render state with another particle part')
    clip = string(key) + u(0) + u(RATE) + u(len(frames_out))
    for frame in frames_out:
        clip += u(len(frame))
        for (kind, tex, src, dst, flags), records in frame:
            clip += b''.join(u(n) for n in (kind, tex, src, dst, flags, len(records)))
            clip += b''.join(f(record) for record in records)
    records = sum(len(r) for frame in frames_out for _, r in frame)
    return clip, dict(link_seconds=seconds, frames=len(frames_out), records=records,
                      parts=[[d['kind'], d['version']] for d in tail['parts']], scale=tail['scale'],
                      thinning=rules)
