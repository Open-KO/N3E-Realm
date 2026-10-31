"""Sample the audited local FX subset into portable timed draw records.

The engine plays bounded camera-facing quads and triangles; legacy FX types,
paths and table IDs remain in the importer/package. Sampling is deterministic
at 30Hz. See ko-effects-skills evidence for the binary motion functions.
"""
import csv
import io
import hashlib
import math
import pathlib
import random
import struct
import ko
import ko_character as character
import ko_fx
import ko_weapon_fx
import appearance_effects
import ko_tiles
from common import f, u, string

RATE = 30


def rgba(value):
    return [(value >> shift & 255) / 255 for shift in (16, 8, 0, 24)]


def fade(age, life, fadein, fadeout):
    if fadein and age < fadein:
        return age / fadein
    if fadeout and age >= fadein + life:
        return max(0, (fadein + life + fadeout - age) / fadeout)
    return 1.


def shape(assets, name, position):
    """The parts of an FX mesh part's shape, each offset by `position`, the
    mesh part's own file position (+0x98, 0047def0).

    PQ-430 (D-220, corrected by PQ-429): 1298 draws an FX mesh with the
    shape's own matrix (0043b650: scale, rotation, then the shape's
    position) times the part's (00480a70). The shape's position is not the
    file's: the mesh part's init 0048ea70 (vtable 006a448c +0x28), which
    ends its load 0048ebf0 and its duplicate 00490540 (run by the bundle
    clone 00478850 that every trigger, 00479de0 and 0047a2d0, makes into a
    fresh bundle whose position 00475060 sets to 0), sets it (0041f740 ->
    0043b650) to the bundle position plus the part position. So the shape
    file's position never reaches the draw, and every vertex is offset by
    the part position in the part's frame: turned by the part's rotation
    and the bundle direction and scaled with the vertex (0048f700, 00490120),
    before 0048fd40 adds the turned current position. A shape rotation, a
    scale other than 1 or animated keys are not drawn here."""
    r = character.Reader(assets.get(name))
    r.string()
    r.floats(3)  # the shape file's position: replaced by 0048ea70
    rotation, scale = r.floats(4), r.floats(3)
    keys = [character.key(r, k) for k in (0, 1, 0)]
    if rotation != [0, 0, 0, 1] or scale != [1, 1, 1] or any(keys):
        raise ValueError('unsupported animated FX shape')
    position = tuple(position)
    if len(position) != 3 or not all(math.isfinite(v) and abs(v) <= 100 for v in position):
        raise ValueError('FX mesh part position')
    if r.string() or r.string():
        raise ValueError('FX collision shape')
    n = r.integer()
    if not 1 <= n <= 16:
        raise ValueError('FX shape part count')
    parts = []
    directory = pathlib.PurePosixPath(name.replace('\\', '/')).parent
    for _ in range(n):
        pivot, mesh_name = r.floats(3), r.string().replace('\\', '/')
        mesh_name = str(directory / pathlib.PurePosixPath(mesh_name).name)
        assets.get(mesh_name)
        path = next(p for p in assets.root.rglob('*.n3pmesh') if p.relative_to(assets.root).as_posix().casefold() == mesh_name.casefold())
        mesh = ko.import_mesh(path, 1)
        material = r.unpack('17f6I')
        if material[:4] != [1, 1, 1, 1] or r.integer() != 1:
            raise ValueError('unsupported FX shape material/texture animation')
        r.floats(1)
        texture = str(directory / pathlib.PurePosixPath(r.string().replace('\\', '/')).name)
        parts.append(dict(pivot=pivot, mesh=mesh, texture=texture, offset=position))
    if any(r.unpack('5i')):
        raise ValueError('FX shape event')
    r.end()
    return parts


def sample_part(d, assets, texture, limit, seed):
    """Return frames of (kind,texture,blend,flags,records) batches.

    Quad record: center3,size2,angle,RGBA4,birth time (-1 follows actor).
    Triangle record: position3,UV2,RGBA4. Z reflection occurs at the boundary.
    """
    if d['ground'] or d['flags'] & ~(199|16|256|512|1024) or d['flags'] & 66 != 66:
        raise ValueError('unsupported FX ground/render flags')
    if d['kind'] == 1 and (d['emit'] != 1 or not 0<=d['emit_param'][0]<=360 or d['animation'] or d['direction'][0] or d['direction'][2] or d['direction'][1] < 0 or any(d['velocity']) or any(d['acceleration'])):
        raise ValueError('unsupported particle emitter motion/direction')
    if d['kind'] == 2 and (d['count'] != 1 or d['only_y'] or d.get('matrix')):
        raise ValueError('unsupported billboard orientation')
    if d['kind'] == 3 and (d['uv'] != [0, 0] or any(d['scale_accel']) or d['rotation'][0] or d['rotation'][2]):
        raise ValueError('unsupported mesh FX motion')
    # PQ-431: 1298's part matrix (0048f440) is the part's own rotation
    # (0048f700) times the turn from +z to the bundle direction (the same
    # function), then times the scale (00490120, 0041dda0 M = M x arg), so it
    # scales along the axes both turns end in. Every 1298 bundle turns (move
    # type -1: about y to the caster's facing or the flattened caster-target
    # direction, 00477590 case 004786ba), and n3e turns a cast clip by the
    # caster's facing after this cook, so the cook's scale in the part's frame
    # agrees with 1298's at every facing only when the x and z scale are equal
    # at every age (a uniform bundle scale changes nothing). A clip cannot
    # carry a facing-dependent scale, so the rest are refused.
    if d['kind'] == 3 and (d['scale'][0] != d['scale'][2] or d['scale_vel'][0] != d['scale_vel'][2]):
        raise ValueError('unsupported FX mesh part scale: x and z differ (1298 scales after the turn to the bundle direction)')
    textures = [texture(d['texture'] + f'{i:04d}.dxt') for i in range(d['textures'])]
    shapes = shape(assets, d['mesh'], d['position']) if d['kind'] == 3 else []
    for s in shapes:
        s['texture_index'] = texture(s['texture'])
    if d['kind'] != 3 and (not textures or d['fps'] <= 0):
        raise ValueError('FX texture sequence')
    rng = random.Random(seed)
    draw = lambda low, high: low + (high-low)*rng.randrange(100)/100
    particles = []
    output = []
    delay = d.get('delay', 0)
    pos, vel = d['position'][:], d['velocity'][:]
    # Initial create delay equals interval, so the first tick emits immediately.
    since = delay
    for frame in range(math.ceil(limit * RATE)):
        t = frame / RATE
        batches = {}
        if t < d['start']:
            output.append([])
            continue
        age = t-d['start']
        for k in range(3):
            vel[k] += d['acceleration'][k]/RATE
            pos[k] += vel[k]/RATE
        def append(kind, tex, record):
            key = kind, tex, *d['blend'], d['flags']
            batches.setdefault(key, []).append(record)
        if d['kind'] == 1:
            since += 1/RATE
            if since + 1e-7 >= delay and (not d['life'] or age < d['life']+d['fadein']):
                since = 0
                for _ in range(min(d['batch'], d['count']-len(particles))):
                    life = draw(*d['particle_life'])
                    size = draw(*d['size'])
                    spread=d['emit_param'][0]
                    angle=math.radians(rng.randrange(int(spread))-spread/2) if spread else 0
                    axis_angle=float(rng.randrange(360)) # authored client's RotationZ uses radians here
                    direction=[math.sin(angle)*math.cos(axis_angle),math.sin(angle)*math.sin(axis_angle),math.cos(angle)]
                    xyz = [draw(a,b) for a,b in zip(d['min'],d['max'])]
                    if d['direction'][1]>0:
                        # +Z emitter rotated to +Y; local XY rectangle becomes XZ.
                        xyz=[xyz[0],xyz[2],-xyz[1]]
                        direction=[direction[0],direction[2],-direction[1]]
                    particles.append(dict(born=t, life=life, size=size, pos=xyz, velocity=[v*d['speed'] for v in direction], drop=0., drop_speed=0.))
            live = []
            for p in particles:
                a = t-p['born']
                total = p['life'] + (0 if d['colors'] else d['fadein']+d['fadeout'])
                if a >= total or total <= 0:
                    continue
                live.append(p)
                angle = a*d['rotate']
                x,y,z = p['pos']
                center = [pos[0]+math.cos(angle)*x+math.sin(angle)*z,
                          pos[1]+y-p['drop'], -(pos[2]-math.sin(angle)*x+math.cos(angle)*z)]
                color = rgba(d['colors'][min(len(d['colors'])-1,int(a/p['life']*len(d['colors'])))]) if d['colors'] else [1,1,1,fade(a,p['life'],d['fadein'],d['fadeout'])]
                size = [max(0,p['size']+a*d.get('size_velocity_'+axis,0)) for axis in ('x','y')]
                tex = textures[int((a+1/RATE)*d['fps']) % len(textures)]
                append(1, tex, center+size+[a*d.get('texture_rotate',0)]+color+[p['born']])
                for k in range(3):p['pos'][k] += p['velocity'][k]/RATE
                # Binary00484980 sets axis/velocity but never particle acceleration
                # (+0x58); keep the initialized zero vector, as in the source.
                p['drop_speed'] += d['gravity']/RATE
                p['drop'] += p['drop_speed']/RATE
            particles = live
        elif d['life'] == 0 or age < d['life']+d['fadein']+d['fadeout']:
            color = [1,1,1,fade(age,d['life'],d['fadein'],d['fadeout'])]
            if d['kind'] == 2:
                index = int(age*d['fps'])
                if d['loop']:
                    index %= len(textures)
                if index < len(textures):
                    motion = d['scale_motion']
                    size = [max(0,d['size'][k]+motion[k]*age+motion[k+2]*age*(age+1/RATE)/2) for k in range(2)]
                    append(1,textures[index],[pos[0],pos[1],-pos[2]]+size+[age*d['rotation'][0]]+color+[-1])
            else:
                angle = age*d['rotation'][1]
                scale = [max(0,d['scale'][k]+d['scale_vel'][k]*age) for k in range(3)]
                for s in shapes:
                    for i in s['mesh']['indices']:
                        v = s['mesh']['vertices'][i]
                        # Mesh importer already reflects Z. Rotate in RH space.
                        # The shape's offset (the part's file position, PQ-430)
                        # is scaled and turned with the vertex; `pos` (that
                        # position plus the part's motion) is added after.
                        # Scaling before the y turn equals 1298's scaling
                        # after it only because x and z scale are equal
                        # (refused above otherwise, PQ-431).
                        x,y,z = [(v[k]+(s['pivot'][k]+s['offset'][k])*(1 if k<2 else -1))*scale[k] for k in range(3)]
                        append(0,s['texture_index'],[math.cos(angle)*x-math.sin(angle)*z+pos[0],y+pos[1],math.sin(angle)*x+math.cos(angle)*z-pos[2]]+v[6:8]+color)
        output.append([(key, records) for key, records in batches.items()])
    return output


TAIL_SECONDS = 2  # a tail link's clip; each link emits for the first half


def main_2233(main, d):
    """PQ-339: a 2233 main bundle (ko_fx.bundle_2233) draws on the FX mesh as
    1298's does. 2233 RenderFX (004304c0) ticks the main bundle (vtable +0x24,
    00580050) without drawing it and reads only its part's render flags
    (+0x324), blends (+0x328, +0x32c), texture sequence (+0x30c, +0x314) and
    frame (+0x390), which the billboard tick 005946a0 sets to int(fps x age) %
    count when it loops, as 1298's does; the bundle's elapsed time (+0x108)
    drives the jitter with 1298's constants (00b90768 1.2, 00b90760 0.07,
    00b90758 0.035). The fields 2233 added are drawn only at the values that
    leave that path as it is (all of them in the 2145 Azagai's bundle); any
    other value is refused, not guessed."""
    if any(main['extra'].values()):
        raise ValueError('2233 weapon effect bundle fields n3e does not draw: %r' % main['extra'])
    if d['cycle'] != [0, 0] or d['texture2'] or d['v6'] or d['v7'] or any(d['v8']) or d['ground']:
        raise ValueError('2233 weapon effect main part fields n3e does not draw')


def appearance_effect(assets, texture, spec, index):
    """One N3E2 entry and its tail clip for an equipped KO weapon effect
    (PQ-211, ko_weapon_fx). `spec`: key, joint, the fx.tbl main/tail files and
    trace colour (ko_weapon_fx.effect) and the FX mesh geometry
    (ko_weapon_fx.geometry). A spec with `layout` '2233' (PQ-339, the 2233
    client's skeletal plug, ko_chrplug_2145.weapon_effects) reads its bundle
    with the 2233 layout and it and its textures from its own `assets` (the
    player's 2145 fx pack), and its tail, when it names one, with
    ko_fx_tail_2233 (PQ-341). Returns (entry, clip key or None, clip bytes)."""
    layout = spec.get('layout', '1298')
    source = spec['assets'] if layout == '2233' else None
    main = ko_fx.bundle((source or assets).get(spec['main']), layout)
    # 00415370 keeps GetPart(0) of the main bundle; 00415910 reads it as a
    # billboard (flags +0x1c0, frame +0x1f0, textures +0x1ac/+0x1b0, blends
    # +0x1c4/+0x1c8). The supported family is the looping, endless one.
    if not main['part_slots'] or main['part_slots'][0] != 0 or main['parts'][0]['kind'] != 2:
        raise ValueError('weapon effect main bundle without a billboard first part')
    d = main['parts'][0]
    if main['life'] or d['life'] or not d['loop'] or not d['textures'] or d['fps'] <= 0:
        raise ValueError('unsupported weapon effect main part')
    if layout == '2233':
        main_2233(main, d)
    # A 1298 spec's texture() takes the name alone, as before PQ-339.
    frames = [texture(d['texture'] + f'{i:04d}.dxt', *([source] if source else [])) for i in range(d['textures'])]
    g = spec['geometry']
    entry = dict(key=spec['key'], joint=spec['joint'], frames=frames, fps=d['fps'],
                 phase_steps=ko_weapon_fx.PHASE_STEPS, phase_step=ko_weapon_fx.PHASE_STEP,
                 blend=list(d['blend']), flags=d['flags'],
                 # 00415910 draws the FX mesh only for an alpha-blended part (flag 1).
                 copies=g['copies'] if d['flags'] & 1 else [],
                 jitter_rate=ko_weapon_fx.JITTER_RATE, jitter_amplitude=ko_weapon_fx.JITTER_AMPLITUDE,
                 jitter=g['jitter'], tail_box=g['tail_box'], tail_low=ko_weapon_fx.TAIL_LOW,
                 tail_steps=ko_weapon_fx.TAIL_STEPS, tail_step=ko_weapon_fx.TAIL_STEP,
                 tails=0, tail_clip='', trace_color=spec['trace_color'])
    if layout == '1298':
        # PQ-376 (D-200): 1298's alpha-list keys, an N3E5 sort record: the
        # copies at the plug origin plus the FX mesh's y extent (00415910),
        # each tail spark on its own (004840b0). The 2233 records keep n3e's
        # order until 2233's own is read.
        entry['sort'] = dict(origin=g['jitter'][0], bias=g['sort_bias'])
    if not spec.get('tail'):
        return entry, None, b''
    if layout == '2233':
        import ko_fx_tail_2233
        key = f'appearance-{spec["key"]}-tail'
        clip, entry['tail_2233'] = ko_fx_tail_2233.tail_clip(source, texture, spec, key)
        entry.update(tails=ko_weapon_fx.TAILS, tail_clip=key)
        return entry, key, clip
    tail = ko_fx.bundle(assets.get(spec['tail']))
    if tail['velocity'] or tail['static'] or tail['life']:
        raise ValueError('unsupported weapon effect tail bundle')
    key = f'appearance-{spec["key"]}-tail'
    frames_out = [[] for _ in range(TAIL_SECONDS * RATE)]
    for i, part in enumerate(tail['parts']):
        if part['kind'] != 1:
            raise ValueError('unsupported weapon effect tail part')
        # 004840b0 queues a spark in the frame's alpha list only when its part
        # alpha-blends (+0x1cc, the flags' bit 0 for base 2, 0047def0); else it
        # draws it at once, before the list, which n3e does not model.
        if not part['flags'] & 1:
            raise ValueError('unsupported weapon effect tail part: no alpha blend')
        part = dict(part)
        # 00484980: with the bundle's scale flag (+0x10c) a particle's size,
        # velocity and creation range take the target scale (+0x110), which
        # 00415370 sets to (FX mesh y + z extent) x 0.7.
        if tail['scale']:
            k = g['tail_scale']
            part.update(size=[v * k for v in part['size']], min=[v * k for v in part['min']],
                        max=[v * k for v in part['max']], speed=part['speed'] * k)
        if max(part['particle_life']) + (0 if part['colors'] else part['fadein'] + part['fadeout']) > TAIL_SECONDS / 2:
            raise ValueError('weapon effect tail particles outlive a link')
        for frame, batches in zip(frames_out, sample_part(part, assets, texture, TAIL_SECONDS, spec['tail_id'] * 31 + i)):
            frame.extend(batches)
    clip = string(key) + u(0) + u(RATE) + u(len(frames_out))
    for frame in frames_out:
        clip += u(len(frame))
        for (kind, tex, src, dst, flags), records in frame:
            clip += b''.join(u(n) for n in (kind, tex, src, dst, flags, len(records)))
            clip += b''.join(f(record) for record in records)
    entry.update(tails=ko_weapon_fx.TAILS, tail_clip=key)
    return entry, key, clip


def cook(assets, definition, out, appearance=(), keys=0, glow=()):
    """effects.bin: N3EF, N3E2 with `appearance` effects (PQ-211), N3E3 when
    `glow` records are given (PQ-315, ko_glow_2233), N3E4 when a 2233 tail
    carries camera-distance particle rules (PQ-342, ko_fx_tail_2233), or N3E5
    when a 1298 effect carries its alpha-list sort record (PQ-376)."""
    rows = {int(r[0]):r for r in csv.reader(io.StringIO(assets.get('Data/fx.tbl.csv').decode('utf-8-sig'))) if r and r[0].isdigit()}
    textures, texture_ids = [], {}
    def texture(name, source=None):
        # A 2233 effect's textures come from its own source (PQ-339), kept
        # apart from the client's by its namespace; only they may be DXT5.
        key = (getattr(source, 'namespace', ''), name.casefold())
        if key not in texture_ids:
            w,h,pixels = ko_tiles.mip_chains((source or assets).get(name), dxt5=source is not None)[0][0]
            if not 1 <= w <= 512 or not 1 <= h <= 512:
                raise ValueError('FX texture bounds')
            texture_ids[key] = len(textures)
            textures.append(u(w)+u(h)+pixels)
        return texture_ids[key]
    clips, report = [], []
    for key, spec in definition['clips'].items():
        row = rows[spec['fx']]
        value = ko_fx.bundle(assets.get(row[2]))
        # PQ-423 (D-220): a clip marked `self` is played as a self FX (move
        # type -1), which follows its joint and never uses the bundle's
        # velocity (00477590, 004786ba-0047871c). PQ-417 (D-222): one marked
        # `flying` is a ranged flight, whose anchor the client moves at the
        # velocity (move type 0); both are cooked in the bundle's frame.
        if (value['velocity'] and not (spec.get('self') or spec.get('flying'))) or value['static']:
            raise ValueError('unsupported moving/static FX bundle')
        if set(spec) - {'fx', 'duration', 'self', 'flying'} or (spec.get('self') and spec.get('flying')):
            raise ValueError('FX clip fields')
        limit = spec['duration']
        if not 0 < limit <= 10:
            raise ValueError('FX clip duration')
        frames = [[] for _ in range(math.ceil(limit*RATE))]
        for i,d in enumerate(value['parts']):
            for frame, batches in zip(frames, sample_part(d,assets,texture,limit,spec['fx']*31+i)):
                frame.extend(batches)
        clip = string(key)+u(value['scale'])+u(RATE)+u(len(frames))
        for frame in frames:
            clip += u(len(frame))
            for (kind,tex,src,dst,flags), records in frame:
                clip += b''.join(u(n) for n in (kind,tex,src,dst,flags,len(records)))
                clip += b''.join(f(record) for record in records)
        clips.append(clip)
        report.append(dict(key=key,fx=spec['fx'],sound=int(row[3]),parts=len(value['parts']),frames=len(frames),slots=value['slots']))
    # PQ-211: effects on equipped appearance keys and their tail clips (N3E2).
    entries, effect_report, tails_2233, thinning, sorts = [], [], {}, [], []
    for index, spec in enumerate(appearance):
        entry, key, clip = appearance_effect(assets, texture, spec, index)
        tail_2233 = entry.pop('tail_2233', None)
        sort = entry.pop('sort', None)
        if sort is not None:
            sorts.append(dict(sort, key=entry['key']))
        if tail_2233 is not None:
            # PQ-341: keys wearing the same 2233 tail on the same FX box share
            # its clip (the bytes after the clip's name are the same, and so
            # are its PQ-342 rules, whose textures are the clip's).
            body = clip[len(string(key)):]
            if body in tails_2233:
                key = entry['tail_clip'] = tails_2233[body]
                clip = None
            else:
                tails_2233[body] = key
                thinning += [dict(rule, clip=key) for rule in tail_2233['thinning']]
            tail_2233 = dict(tail_2233, clip=entry['tail_clip'])
        entries.append(entry)
        if clip:
            clips.append(clip)
        effect_report.append(dict(key=spec['key'], item=spec['ko_item'], main=spec['main'], main_id=spec['main_id'],
                                  **({'layout': '2233'} if spec.get('layout') == '2233' else {}),
                                  tail=spec.get('tail'), frames=len(entry['frames']), copies=len(entry['copies']),
                                  triangles=sum(len(c['vertices']) for c in entry['copies']) // 3,
                                  tails=entry['tails'], trace_color=f'{spec["trace_color"]:08x}',
                                  tail_scale=spec['geometry']['tail_scale'],
                                  **({'sort': sort} if sort else {}),
                                  **({'tail_2233': tail_2233} if tail_2233 else {})))
    data = b'N3EF'+u(len(textures))+b''.join(textures)+u(len(clips))+b''.join(clips)
    bindings=definition['bindings']
    data+=u(len(bindings))
    for b in bindings:
        if b['kind'] not in (1,2,3) or b['selector'] not in range(5) or b['anchor'] not in range(130) or not 1<=len(b['clips'])<=8 or any(c not in definition['clips'] for c in b['clips']):
            raise ValueError('effect binding')
        data+=u(b['kind'])+string(b['key'])+u(b['selector'])+u(b['anchor'])+u(len(b['clips']))+b''.join(string(c) for c in b['clips'])
    if sorts:
        # PQ-376 (D-200): the 1298 effects' alpha-list keys (N3E5).
        data = appearance_effects.n3e5(data, entries, list(glow), thinning, sorts, keys)
    elif thinning:
        # PQ-342: the 2233 tails' camera-distance particle rules (N3E4).
        data = appearance_effects.n3e4(data, entries, list(glow), thinning, keys)
    elif glow:
        data = appearance_effects.n3e3(data, entries, list(glow), keys)
    elif entries:
        data = appearance_effects.n3e2(data, entries, keys)
    if len(data) > 16*1024*1024:
        raise ValueError('FX package byte bound')
    out.write_bytes(data)
    return dict(clips=report,textures=len(textures),bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),sources=assets.sources.copy(),sampling_hz=RATE,
                appearance=effect_report)
