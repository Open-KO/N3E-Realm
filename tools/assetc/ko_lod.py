"""Binary-grounded world LOD cooking. Runtime records contain no legacy paths.

PMesh: 00441820/00441960/00441a50. Terrain: 0059b430/0059b510/005a0410.
Color-map records: 0059eff0, x-major then z; UV inset: 005a0410.
"""
from common import *
import ko_tiles
import ko_normals
import world_chunks


class WorldTooLarge(ValueError):
    """A built world exceeds an N3W1 / N3L3 bound; the KO bake then writes
    N3W2 instead (PQ-234). The message is the bound's own."""


def bounds(points):
    lo = [min(p[a] for p in points) for a in range(3)]
    hi = [max(p[a] for p in points) for a in range(3)]
    return [(a+b)/2 for a,b in zip(lo,hi)], math.dist(lo,hi)/2


def fan_cells(level, mask):
    """Original algorithm: mask bits request a refined outer edge (L,T,R,B)."""
    cell = 1 << level
    for x in range(0,8,cell):
        for z in range(0,8,cell):
            center=(x+cell//2,z+cell//2)
            corners=[(x,z),(x,z+cell),(x+cell,z+cell),(x+cell,z)]
            ring=[]
            for side,(a,b) in enumerate(zip(corners,corners[1:]+corners[:1])):
                outer=(x==0,z+cell==8,x+cell==8,z==0)[side]
                step=(1 if level==2 else 4) if outer and mask & (1<<side) else cell
                for k in range(0,cell,step):
                    ring.append((a[0]+(b[0]-a[0])*k//cell,a[1]+(b[1]-a[1])*k//cell))
            for a,b in zip(ring,ring[1:]+ring[:1]):
                yield center,a,b


def color_map_region(tx, tz, width):
    """The colour-map texture of reference tile (tx, tz) on a `width`-tile map.

    `0059eff0` reads `ko_tiles.color_map_side` squared textures x-major (the
    pointer array `+0x4190` by x, each row `0x50`-byte textures by z), and
    `0059b890` points patch `+0x2c` at entry `[px * 32 >> 7][pz * 32 >> 7]`
    for the patch at tile (px * 8, pz * 8): one texture per 32-tile region.
    Both patch levels of `005a2640` draw that pointer (`005a2726`, `005a29e1`)."""
    side=ko_tiles.color_map_side(width//8)
    return (tx//32)*side+tz//32


def near_color_uv(tx, tz):
    """`005a0410`'s level-1 colour-map UVs of reference tile (tx, tz), for the
    corners (tx, tz), (tx, tz+1), (tx+1, tz+1), (tx+1, tz).

    The tick gives them to a tile whose tex1 is above the tile-texture count or
    whose full bit is clear (`005a067c`..`005a0794`): u at tx is
    ((tx % 32) * 3.9375 + 1) / 128 and v at tz ((32 - tz % 32) * 3.9375 + 1) / 128
    (the constants `006a8320`, `006a3a64`, `006a831c`), the inset
    UVConvert(t) = (126 t + 1) / 128. The far edge converts the already
    converted value again: u at tx + 1 is (u * 126 + 4.9375) / 128, v at tz + 1
    ((v - 1 / 32) * 126 + 1) / 128 (`006a8318`, `006a8314`, `006a8310`), as
    Open-KO/KnightOnline's UVConvert(u1[0] + 1/32) also reads. Every step is exact in
    float32."""
    left=((tx%32)*3.9375+1.0)*0.0078125
    right=(left*126.0+4.9375)*0.0078125
    top=((32-tz%32)*3.9375+1.0)*0.0078125
    bottom=((top-0.03125)*126.0+1.0)*0.0078125
    return [(left,top),(left,bottom),(right,bottom),(right,top)]


def terrain(color_map, height, atlas, vertices, indices, clear):
    """Bake all 16 edge masks at levels 2/3, preserving level-1 tile artwork.

    `color_map` is the zone's TCT (Zones.tbl column 4, `ko_zone`): a grid of
    `ko_tiles.color_map_side(patches)` textures a side (0059eff0).
    """
    n=height['width']; width=n-1
    if width%8: raise ValueError('color-map grid must cover whole 32-tile regions')
    side=ko_tiles.color_map_side(width//8)
    count=side*side
    # An atlas draws the 104-square images; a slot table (the N3W2 bake,
    # ko_scene.Slots) only checks the grid and takes native chains later.
    colors=ko_tiles.tiles(read(pathlib.Path(color_map),ko_tiles.color_map_limit(count)),
                          wanted=None if atlas.draws else set(),target=104,count=count)
    slots=[atlas.add(('color-map',i),lambda i=i:colors[i]) for i in range(count)]
    ox,oy,oz=height['origin']; spacing=height['spacing']; chunks=[]
    def point(x,z):
        gz=width-z
        return [ox+x*spacing,oy+height['heights'][gz*n+x],oz+gz*spacing]
    normals=ko_normals.normals(height)
    def normal(x,z): return normals[(width-z)*n+x]
    for z in range(0,width,8):
        for x in range(0,width,8):
            near=[i for gz in range(width-z-8,width-z) for gx in range(x,x+8)
                  for i in indices[(gz*width+gx)*6:(gz*width+gx+1)*6]]
            c,r=bounds([point(x+dx,z+dz) for dx in range(9) for dz in range(9)])
            levels=[(0.,near)]; cache={}
            slot=slots[color_map_region(x,z,width)]
            def vertex(p):
                if p not in cache:
                    gx,gz=x+p[0],z+p[1]
                    # UVConvert: (126*u+1)/128; never wrap the region's upper edge.
                    uv=[((gx-x//32*32)/32*126+1)/128,
                        ((1-(gz-z//32*32)/32)*126+1)/128]
                    cache[p]=len(vertices)
                    vertices.append(point(gx,gz)+normal(gx,gz)+uv+[.5,.5,float(slot),float(clear)])
                return cache[p]
            for level in (2,3):
                for mask in range(16):
                    ix=[]
                    for center,a,b in fan_cells(level,mask):
                        # Reflection reverses the original fan winding.
                        ix.extend(vertex(p) for p in (center,b,a))
                    levels.append((float(len(levels)),ix))
            chunks.append(dict(center=c,radius=r,scale=1.,flags=2,levels=levels,
                               kind=2,patch=[x//8,z//8]))
    return chunks,dict(origin=[ox,oy,oz+width*spacing],patch_size=8*spacing,
                       far_factor=3/512,minimum=2,band=3,bias=.6,
                       width=width//8)


def serialize(built):
    """N3L3, or N3L4 when a part is an alpha part (D-201, PQ-379): N3L3 with
    each alpha part's record after its kind's fields (world_chunks.alpha_bytes);
    N3L5 when a part sets the opaque bits 5 or 6 (D-202, PQ-382). No N3L file
    carries a texture sequence (D-212, PQ-394): only N3W6 does."""
    if world_chunks.has_sequence(built['chunks']):raise ValueError('N3L files cannot carry texture sequences (N3W6, D-212)')
    out=bytearray((b'N3L3',b'N3L4',b'N3L5')[world_chunks.layout(built['chunks'])]); cfg=built['terrain_lod']
    out+=f([*cfg['origin'],cfg['patch_size'],cfg['far_factor'],cfg['bias']])
    out+=u(cfg['minimum'])+u(cfg['band'])+u(cfg['width'])
    parents=built['parents']; out+=u(len(parents))
    for p in parents: out+=f(p)
    out+=u(len(built['chunks']));total=0
    for p in built['chunks']:
        out+=f([*p['center'],p['radius'],p['scale']])+u(p['flags'])+u(len(p['levels']))
        for d,ix in p['levels']:
            total+=len(ix);out+=f([d])+u(len(ix))+b''.join(u(i) for i in ix)
        out+=u(p['kind'])
        if p['kind']==2:
            out+=u(p['patch'][0])+u(p['patch'][1])+world_chunks.alpha_bytes(p);continue
        pm=p['progressive'];out+=u(p['parent'])+u(p['base'])
        out+=u(pm['min_vertices'])+u(pm['min_indices'])+u(p['max_vertices'])
        out+=u(len(pm['controls']))
        for d,budget in pm['controls']:out+=f([d])+u(budget)
        out+=u(len(pm['splits']))
        for di,dc,dv,first,group,target in pm['splits']:
            out+=b''.join(u(i) for i in (di,dc,dv,first,group,target))
        out+=u(len(pm['edits']))+b''.join(u(i) for i in pm['edits'])
        out+=world_chunks.alpha_bytes(p)
    if total>2000000 or len(out)>16*1024*1024:raise WorldTooLarge('world LOD budget')
    return out
