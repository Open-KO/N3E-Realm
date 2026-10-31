"""An original synthetic 2233 weapon effect tail for the PQ-341 checks, in the
2233 FX bundle layout (ko_fx.bundle_2233). Original n3e implementation; no
imported assets.

The tail is shaped like the Azagai's (fx.tbl 32121) but holds none of its
bytes: an FX bundle version 4 with the scale flag set; two mesh parts (part
version 8, base 3) turning at -9 and +9 rad/s about all three axes, scale 0.9
and 0.7, the version-6 byte set (their shape's frames wrap) at 15 and 40
frames a second, each drawing one shape (a small octahedron with a uniform
scale track of 50 keys at 30 a second: 1, then 0.5 for keys 20-29); and two
particle parts (part version 9, base 3): emitter kind 2 toward a target point
3 m along +z (turned to +y: upward), and emitter kind 1 with a 360 degree
spread, both on direction +y with the version-9 distances set (40 and 70 m,
as the Azagai's kind-2 parts) and each with its own green texture (PQ-342: a
camera-distance rule applies to one particle batch material). parts(lime=...)
gives the kind-1 part other version-9 distances, and parts(red=...) adds a
third particle part (kind 2, a red texture, 0.6 m along +x from the others)
with the given ones. Every texture is a 4 x 4 DXT5 with no
mips, followed by the w/2 x h/2 16-bit level the 2145 fx pack's no-mip
textures carry.

files() returns the files by the names the bundle and shapes give them, as a
2145 fx pack Source would (ko_chrplug_2145.Source keys them with '\\')."""
import struct

TAIL = 'fx\\tail_2233.fxb'
SHAPES = ('fx\\object\\a\\shape.n3shape', 'fx\\object\\b\\shape.n3shape')
TEXTURE = 'fx\\particle\\green_'
LIME = 'fx\\particle\\lime_'
RED_TEXTURE = 'fx\\particle\\red_'
GREEN, RED = (0, 255, 0), (255, 0, 0)
# The version-9 distances (40.0 and 70.0 m) as the u32 bits the bundle holds.
DISTANCES = (1109393408, 1116471296)
KEYS = 50


def pack(fmt, *values):
    return struct.pack('<' + fmt, *values)


def path(text):
    return text.encode() + bytes(260 - len(text))


def string(text):
    return pack('I', len(text)) + text.encode()


def base(kind, version, textures, fps, texture='', fadeout=0., fadein=0., rotation=(0, 0, 0), flags=0x1c7,
         position=(0, 0, 0)):
    """A 2233 part base (00589370), base version 3: life 0, no on/off cycle."""
    return (pack('BBf', version, 3, 0) + pack('2f', 0, 0) + pack('B', kind) + pack('6f', *[0] * 6)
            + pack('3f', *rotation) + b'\0' + pack('3f', *position) + pack('if', textures, fps) + path(texture)
            + pack('IIffI', 5, 2, fadeout, fadein, flags))


def mesh_part(shape, rotation, scale, meshfps, wrap=1, **change):
    """A mesh part (0059b3f0), part version 8."""
    d = dict(uvdir=0, uv=(0, 0), scale_vel=(0, 0, 0), scale_accel=(0, 0, 0), v7=0, v8=0)
    d.update(change)
    return (base(3, 8, 0, 1, rotation=rotation) + path(shape)
            + pack('B2f3f', d['uvdir'], *d['uv'], *d['scale_vel']) + b'\1' + pack('3f', *d['scale_accel'])
            + pack('f', meshfps) + pack('3f', scale, scale, scale) + pack('BBB', wrap, d['v7'], d['v8']))


def particle_part(emit, params, speed, life=(.3, .2), size=(.12, .1), count=12, delay=.05, texture=TEXTURE,
                  **change):
    """A particle part (00593550), part version 9, on direction +y."""
    d = dict(v6=0, v7=0, v8=(0, 0, 0, 0), v9=DISTANCES, direction=(0, 1, 0), fadein=.1, fadeout=.2, textures=1,
             batch=1, position=(0, 0, 0))
    d.update(change)
    out = base(1, 9, d['textures'], 0, texture=texture, fadeout=d['fadeout'], fadein=d['fadein'],
               position=d['position'])
    out += pack('I2f2f3f3ffII', count, *size, *life, -.03, -.03, -.03, .03, .03, .03, delay, d['batch'], emit)
    out += pack('%df' % len(params), *params) + pack('3f', *d['direction'])
    out += pack('4f', speed, 0, 1.5, 1) + b'\0\0' + pack('3f', 2, -.05, -.05)
    out += pack('B', d['v6']) + pack('B', d['v7']) + pack('B3I', *d['v8']) + pack('2I', *d['v9'])
    return out


def bundle(parts, scale=1, life=0., velocity=0., trailing=b'\0' + b'\0' + pack('I', 0) + pack('I', 0) + b'\0'):
    """A version-4 bundle (0057f0b0): its parts in slots 0.., then the fields
    versions 2-4 add, all zero, and 2 unread zero bytes."""
    out = pack('iffB', 4, life, velocity, scale)
    for i in range(26):
        out += pack('If', parts[i][0], 0) + parts[i][1] if i < len(parts) else pack('i', 0)
    return out + trailing + b'\0\0'


def bits(value):
    """A version-9 distance as the u32 bits the bundle holds."""
    return struct.unpack('<I', struct.pack('<f', value))[0]


def parts(lime=None, red=None):
    """The tail's parts; `lime` (near, far) for the kind-1 part's distances,
    `red` (near, far) adds the red particle part."""
    out = [(3, mesh_part(SHAPES[0], (-9, -9, -9), .9, 15)), (3, mesh_part(SHAPES[1], (9, 9, 9), .7, 40)),
           (1, particle_part(2, (0, 0, 3), .5)),
           (1, particle_part(1, (360,), .4, texture=LIME, **({'v9': tuple(bits(v) for v in lime)} if lime else {})))]
    if red:
        out.append((1, particle_part(2, (0, 0, 3), .5, texture=RED_TEXTURE, size=(.24, .2), position=(.6, 0, 0),
                                     v9=tuple(bits(v) for v in red))))
    return out


def pmesh():
    """An octahedron 0.08 m from its centre (8 triangles), normals outward."""
    r = .08
    points = [(r, 0, 0), (-r, 0, 0), (0, r, 0), (0, -r, 0), (0, 0, r), (0, 0, -r)]
    vertices = [list(p) + [x / r for x in p] + [.5 + p[0] / (2 * r), .5 + p[1] / (2 * r)] for p in points]
    faces = [(0, 2, 4), (2, 1, 4), (1, 3, 4), (3, 0, 4), (2, 0, 5), (1, 2, 5), (3, 1, 5), (0, 3, 5)]
    indices = [i for face in faces for i in face]
    return (string('octahedron') + pack('6i', 0, 0, len(vertices), len(indices), len(vertices), len(indices))
            + pack('%df' % (8 * len(vertices)), *[x for v in vertices for x in v])
            + pack('%dH' % len(indices), *indices) + pack('i', 0))


def shape(keys=None, rate=30.):
    """A CN3FXShape: at the origin, a uniform scale track, one part naming
    object\\octahedron.n3pmesh and object\\green_0000.dxt (found in the
    shape's own folder, 0058c630)."""
    keys = keys or [1.0 if not 20 <= i < 30 else .5 for i in range(KEYS)]
    out = string('shape') + pack('3f', 0, 0, 0) + pack('4f', 0, 0, 0, 1) + pack('3f', 1, 1, 1)
    out += pack('i', 0) + pack('i', 0) + pack('iif', len(keys), 0, rate)
    out += b''.join(pack('3f', k, k, k) for k in keys)
    out += pack('I', 0) + pack('I', 0) + pack('i', 1) + pack('3f', 0, 0, 0) + string('object\\octahedron.n3pmesh')
    out += pack('17f', *[1] * 4 + [0] * 13) + pack('6I', 0, 0, 0, 0, 0, 0) + pack('i', 1) + pack('f', 0)
    return out + string('object\\green_0000.dxt') + pack('5i', 0, 0, 0, 0, 0)


def texture(rgb=GREEN):
    """A 4 x 4 DXT5 with no mips: opaque, one colour (RGB565 end points), then
    the 2145 fx pack's no-mip remainder (w/2 x h/2 x 2 bytes)."""
    c = (rgb[0] >> 3) << 11 | (rgb[1] >> 2) << 5 | rgb[2] >> 3
    block = bytes([255, 255]) + bytes(6) + pack('HHI', c, c, 0)
    return pack('i', 0) + b'NTF\x03' + pack('4i', 4, 4, 0x35545844, 0) + block + bytes(2 * 2 * 2)


def files(tail=None):
    out = {TAIL: tail or bundle(parts()), TEXTURE + '0000.dxt': texture(), LIME + '0000.dxt': texture(),
           RED_TEXTURE + '0000.dxt': texture(RED)}
    for name in SHAPES:
        folder = name.rsplit('\\', 1)[0]
        out[name] = shape()
        out[folder + '\\octahedron.n3pmesh'] = pmesh()
        out[folder + '\\green_0000.dxt'] = texture()
    return out


class Source:
    """The files as a 2145 fx pack Source gives them (names with '/' or '\\')."""

    namespace = 'synthetic-2233'

    def __init__(self, files):
        self.files = files

    def get(self, name):
        return self.files[name.replace('/', '\\')]
