"""Terrain sample normals from client 0059a690, reflected into n3e coordinates.

The odd-parity third wedge reuses the south height for both vectors in the
binary (0059a7fe–0059a819). Preserve that observed arithmetic, not the incomplete
commented-out source algorithm. No post-average normalization occurs there.
"""
import math
import struct

def f32(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]

def normals(height):
    n=height['width']; h=height['heights']; spacing=height['spacing']
    result=[]
    # Heights have already been reflected in Z. Use source-grid parity.
    def sample(x,z): return h[(n-1-z)*n+x]
    for gz in range(n):
        z=n-1-gz
        for x in range(n):
            if x in (0,n-1) or z in (0,n-1):
                result.append([0.,1.,0.]); continue
            ring=[(0,1),(1,1),(1,0),(1,-1),(0,-1),(-1,-1),(-1,0),(-1,1)]
            if (x+z)&1: ring=ring[::2]
            total=[0.,0.,0.]; center=sample(x,z)
            for j,(a,b) in enumerate(zip(ring,ring[1:]+ring[:1])):
                ah=sample(x+a[0],z+a[1])-center
                bh=sample(x+b[0],z+b[1])-center
                if (x+z)&1 and j==2: bh=f32(ah)
                va=[a[0]*spacing,ah,a[1]*spacing]
                vb=[b[0]*spacing,bh,b[1]*spacing]
                cross=[f32(va[1]*vb[2]-va[2]*vb[1]),
                       f32(va[2]*vb[0]-va[0]*vb[2]),
                       f32(va[0]*vb[1]-va[1]*vb[0])]
                length=f32(math.sqrt(sum(v*v for v in cross)))
                for k in range(3): total[k]=f32(total[k]+cross[k]/length)
            result.append([f32(total[0]/len(ring)), f32(total[1]/len(ring)), -f32(total[2]/len(ring))])
    return result
