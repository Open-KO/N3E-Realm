"""Compare a single world frame before/after marker drawing (no HUD/time drift)."""
import pathlib,sys


def verify(prefix):
    def read(suffix):
        data=pathlib.Path(str(prefix)+suffix).read_bytes()
        magic,size,maximum,pixels=data.split(b'\n',3)
        assert magic==b'P6' and maximum==b'255'
        width,height=map(int,size.split());assert len(pixels)==width*height*3
        return width,height,pixels
    w,h,before=read('.world-without-marker.ppm');w2,h2,after=read('.world-with-marker.ppm')
    assert (w,h)==(w2,h2)
    rows={}
    for y in range(h):
        count=0
        for x in range(w):
            at=(y*w+x)*3;r,g,b=(after[at+i]-before[at+i]for i in range(3))
            count+=g>5 and g>r+3 and g>b+3
        if count:rows[y]=count
    bands=[]
    for y,count in rows.items():
        if not bands or y>bands[-1][1]+4:bands.append([y,y,count])
        else:bands[-1][1]=y;bands[-1][2]+=count
    assert len(bands)==2 and all(row[2]>=20 for row in bands),bands
    print('PASS GPU separate green arrow/ring contributions: '+str(bands))
    return bands


if __name__=='__main__':verify(sys.argv[1])
