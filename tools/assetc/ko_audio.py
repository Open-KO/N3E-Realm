"""Cook audited KO sound references into bounded mono PCM and event bindings."""
import csv, hashlib, io, json, math, struct, wave
from pathlib import Path
from common import u, f, string
import audio_spatial, ko_character

RATE=48000

def pcm(data):
    if len(data)>4*1024*1024:raise ValueError('WAV byte bound')
    with wave.open(io.BytesIO(data)) as w:
        channels,width,rate,frames,compression,_=w.getparams()
        if channels not in (1,2) or width not in (1,2,3,4) or not 8000<=rate<=96000 or not 0<frames<=rate*10 or compression!='NONE':raise ValueError('WAV format/bounds')
        raw=w.readframes(frames)
    if len(raw)!=frames*channels*width:raise ValueError('truncated WAV')
    source=[]
    for frame in range(frames):
        value=0
        for channel in range(channels):
            offset=(frame*channels+channel)*width
            sample=int.from_bytes(raw[offset:offset+width],'little',signed=width>1)
            value+=(sample-128)/128 if width==1 else sample/(1<<(width*8-1))
        source.append(value/channels)
    output=[]
    for i in range(math.ceil(frames*RATE/rate)):
        position=i*rate/RATE;index=min(int(position),frames-1);fraction=position-index
        value=source[index]*(1-fraction)+source[min(index+1,frames-1)]*fraction
        output.append(max(-32768,min(32767,round(value*32768))))
    return struct.pack('<'+'h'*len(output),*output)

def cook(assets,effects,hud,out,item_icons=None,extra=None):
    # `item_icons`: the package's item icon map when it is not ui.json's (PQ-321).
    # `extra`: further keys bound to sound.tbl ids (PQ-417: the glow bow's release).
    rows={int(r[0]):r for r in csv.reader(io.StringIO(assets.get('Data/sound.tbl.csv').decode('utf-8-sig'))) if r[0].isdigit()}
    clips=[];ids={};bindings={};report=[]
    def sound(path,maximum):
        key=path.replace('\\','/').lower()
        if key not in ids:
            samples=pcm(assets.get(path));ids[key]=len(clips)
            clips.append(u(maximum)+u(len(samples)//2)+samples)
            report.append(dict(path=path,maximum=maximum,frames=len(samples)//2))
        return ids[key]
    def bind(key,ident):
        row=rows[ident];bindings[key]=sound(row[1],min(16,max(1,int(row[3]))))
    for clip in effects['clips']:
        if clip['sound']>0:bind('effect:'+clip['key'],clip['sound'])
    for key,ident in (extra or {}).items():
        if key in bindings or key.startswith('effect:'):raise ValueError('audio key %r is taken'%key)
        bind(key,ident)
    for key,ident in {'swing:player':14,'swing:npc':104010,'struck:player':16,'struck:npc':104210,'blow':100,'loot:coins':3000,'loot:default':2000,'item:default':2000}.items():bind(key,ident)
    spec=json.loads(Path('games/moradon/ui.json').read_text())
    for item,ident in (spec['item_icons'] if item_icons is None else item_icons).items():
        # Package icon families select weapon/armor/general UI sounds.
        # Binary00578780 uses full item IDs /100000000; icon IDs are not item IDs.
        ident=int(ident) if isinstance(ident,(int,str)) else int(ident['base'])
        group=ident//10000000
        for prefix in ('loot:','item:'):bind(prefix+item,2002 if group==1 else 2003 if group==2 else 2000)
    for control,paths in hud['sounds'].items():
        for event,path in zip(('hover:','click:'),paths):
            if path:bindings[event+str(control)]=sound(path,9)
    player=ko_character.animations(assets.get('Chr/upc_ka_tu.n3Anim'))
    npc=ko_character.animations(assets.get('Chr/mob_worm.n3anim'))
    config=json.loads(Path('games/moradon/combat-animation.json').read_text())
    timings=[]
    def markers(clip):
        return [clip['blend_seconds']+(n-clip['start'])/clip['fps'] for n in clip['sound'] if clip['start']<n<=clip['end']]
    for style,profile in enumerate(config['profiles'],1):
        for variant,index in enumerate(profile['attacks'],1):timings.append((style,variant,markers(player[index])))
        timings.append((style,3,markers(player[profile['moving']])))
    timings.append((0,4,markers(npc[4])))
    # KO positional policy (PQ-013): the effect start test of 00475d20 at
    # Sound.Distance (Option.ini, default 48, clamp 20-48: 0064b9b0, 006453b0)
    # and the player listener of 00646550.
    spatial=audio_spatial.cook(json.loads(Path('games/moradon/audio.json').read_text()))
    data=b'N3A2'+u(RATE)+u(len(clips))+b''.join(clips)+u(len(bindings))
    for key,index in sorted(bindings.items()):data+=string(key)+u(index)
    data+=u(len(timings))
    for style,variant,times in timings:data+=u(style)+u(variant)+u(len(times))+f(times)
    data+=spatial
    if len(data)>16*1024*1024:raise ValueError('audio package bound')
    out.write_bytes(data)
    return dict(clips=report,bindings=bindings,timings=timings,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),sources=assets.sources.copy())
